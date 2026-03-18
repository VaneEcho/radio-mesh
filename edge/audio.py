"""
RF·MESH Edge — Audio Demodulation Streamer
==========================================
Captures demodulated audio from a spectrum analyser and streams PCM chunks
to the Cloud backend via the heartbeat WebSocket.

Two operating modes
-------------------
hardware (``audio.mode: hardware``)
    Receives pre-demodulated PCM audio from the EM550 Annex E UDP stream.
    The EM550 pushes raw PCM over UDP after the operator starts a CW + demod
    task.  This path has the lowest latency and best audio quality.

software (``audio.mode: software``)
    Performs IQ capture via RSA306B (or any driver exposing
    ``if_analysis_iq()``) and applies numpy/scipy software demodulation
    (AM / FM / USB / LSB) from ``edge/demod.py``.
    Works without EM550 Annex E hardware option.

Time alignment
--------------
Every audio chunk sent to Cloud includes a ``timestamp_ms`` that matches the
Unix-ms timestamp of the contemporaneous spectrum frame produced by the
scanner at the same moment.  The frontend uses this to align the audio
playback position with the displayed spectrum waterfall.

Configuration (config.yaml)
---------------------------
audio:
  enabled: true
  mode: hardware         # hardware | software
  udp_host: ""           # bind address for EM550 UDP (empty = all interfaces)
  udp_port: 5556         # UDP port where EM550 pushes Annex E audio
  sample_rate: 16000     # output PCM sample rate sent to Cloud
  demod_mode: FM         # FM | AM | USB | LSB | CW  (software mode only)
  center_hz: 97400000    # IF Analysis centre frequency (software mode only)
  span_hz: 400000        # IQ capture span in Hz (software mode only)
  chunk_duration_s: 0.1  # seconds of audio per chunk (hardware: UDP accumulation window)

Usage (called from edge/main.py)
---------------------------------
    audio = AudioStreamer(cfg=cfg, heartbeat=heartbeat, driver=scanner.driver)
    audio.start()
    ...
    audio.stop()
"""
from __future__ import annotations

import base64
import logging
import queue
import socket
import struct
import threading
import time
from typing import TYPE_CHECKING

import numpy as np

from .demod import demodulate, get_optimal_iq_sample_rate

if TYPE_CHECKING:
    from .heartbeat import Heartbeat
    from .scanner import Scanner

log = logging.getLogger(__name__)


class AudioStreamer:
    """
    Background thread that streams demodulated audio chunks to Cloud.

    Parameters
    ----------
    cfg:       Full parsed config.yaml dict.
    heartbeat: Heartbeat instance (used to send audio chunks).
    scanner:   Scanner instance.  ``scanner.driver`` is read after the device
               connects (set inside ``scanner.run()``).  Software mode waits
               up to 30 s for the driver to become available.
    """

    def __init__(
        self,
        cfg: dict,
        heartbeat: "Heartbeat",
        scanner: "Scanner | None" = None,
    ) -> None:
        audio_cfg = cfg.get("audio", {})
        self._enabled: bool = audio_cfg.get("enabled", False)
        self._mode: str = audio_cfg.get("mode", "software").lower()

        # Hardware (EM550 Annex E) settings
        self._udp_host: str = audio_cfg.get("udp_host", "")
        self._udp_port: int = int(audio_cfg.get("udp_port", 5556))

        # Software (IQ capture + demod) settings
        self._demod_mode: str = audio_cfg.get("demod_mode", "FM").upper()
        self._center_hz: float = float(audio_cfg.get("center_hz", 97_400_000))
        self._span_hz: float = float(audio_cfg.get("span_hz", 400_000))

        # Common
        self._target_rate: int = int(audio_cfg.get("sample_rate", 16_000))
        self._chunk_duration_s: float = float(audio_cfg.get("chunk_duration_s", 0.1))

        self._heartbeat = heartbeat
        self._scanner = scanner
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    # ── Public API ────────────────────────────────────────────────────────────

    def start(self) -> None:
        if not self._enabled:
            log.info("AudioStreamer disabled (audio.enabled=false)")
            return
        target = self._run_hardware if self._mode == "hardware" else self._run_software
        self._thread = threading.Thread(target=target, name="audio", daemon=True)
        self._thread.start()
        log.info(
            "AudioStreamer started: mode=%s sample_rate=%d Hz",
            self._mode, self._target_rate,
        )

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)

    # ── Hardware mode (EM550 Annex E UDP) ─────────────────────────────────────

    def _run_hardware(self) -> None:
        """
        Listen for EM550 Annex E PCM UDP packets and relay to Cloud.

        The EM550 streams raw PCM (S16LE, mono) over UDP.  We accumulate
        packets into chunks of _chunk_duration_s seconds, then send via
        heartbeat.

        Note: Exact Annex E packet format should be validated against the
        EM550 manual.  This implementation assumes:
          - No packet header (raw PCM bytes)
          - 16-bit signed PCM, little-endian, mono
          - Sample rate = self._target_rate (confirmed from EM550 config)
        """
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        bind_addr = (self._udp_host, self._udp_port)
        try:
            sock.bind(bind_addr)
        except OSError as exc:
            log.error("AudioStreamer: cannot bind UDP %s:%d — %s", *bind_addr, exc)
            return

        sock.settimeout(1.0)
        log.info("AudioStreamer: listening for EM550 Annex E on UDP %s:%d", *bind_addr)

        # Accumulate samples for one chunk
        samples_per_chunk = int(self._target_rate * self._chunk_duration_s)
        accumulator: list[np.ndarray] = []
        accumulated = 0

        while not self._stop_event.is_set():
            try:
                data, _ = sock.recvfrom(65536)
            except socket.timeout:
                continue
            except Exception as exc:
                log.warning("AudioStreamer: UDP recv error: %s", exc)
                continue

            if len(data) % 2 != 0:
                data = data[:-1]  # trim to even bytes

            if len(data) == 0:
                continue

            chunk = np.frombuffer(data, dtype="<i2")  # int16 LE
            accumulator.append(chunk)
            accumulated += len(chunk)

            if accumulated >= samples_per_chunk:
                pcm = np.concatenate(accumulator)[:samples_per_chunk]
                self._send_chunk(pcm)
                accumulator = []
                accumulated = 0

        sock.close()
        log.info("AudioStreamer: hardware mode stopped")

    # ── Software mode (IQ capture + demod) ────────────────────────────────────

    def _get_driver(self, wait_s: float = 30.0):
        """
        Return the driver from the scanner, waiting until it is connected.
        Returns None if the driver never becomes available within wait_s.
        """
        if self._scanner is None:
            return None
        deadline = time.monotonic() + wait_s
        while time.monotonic() < deadline and not self._stop_event.is_set():
            drv = getattr(self._scanner, "driver", None)
            if drv is not None:
                return drv
            self._stop_event.wait(timeout=0.5)
        return None

    def _run_software(self) -> None:
        """
        Continuously capture IQ samples from driver and demodulate to PCM.

        Each iteration:
          1. driver.if_analysis_iq() → IQ block
          2. demodulate() → PCM int16
          3. heartbeat.send_audio_chunk() → Cloud → frontend
        """
        driver = self._get_driver(wait_s=30.0)
        if driver is None:
            log.error("AudioStreamer: no driver available after 30 s — stopping software mode")
            return

        if not hasattr(driver, "if_analysis_iq"):
            log.error(
                "AudioStreamer: driver %r does not support if_analysis_iq() "
                "— software demod not available",
                driver,
            )
            return

        suggested_span = get_optimal_iq_sample_rate(self._target_rate, self._demod_mode)
        span = self._span_hz if self._span_hz > 0 else suggested_span
        log.info(
            "AudioStreamer software: center=%.3f MHz span=%.1f kHz mode=%s",
            self._center_hz / 1e6, span / 1e3, self._demod_mode,
        )

        while not self._stop_event.is_set():
            t0 = time.monotonic()
            try:
                _, iq, sample_rate = driver.if_analysis_iq(
                    center_hz=self._center_hz,
                    span_hz=span,
                    duration_s=self._chunk_duration_s,
                )

                if len(iq) == 0:
                    log.debug("AudioStreamer: empty IQ block — skipping")
                    self._stop_event.wait(timeout=0.05)
                    continue

                pcm = demodulate(
                    iq,
                    sample_rate=sample_rate,
                    mode=self._demod_mode,
                    target_rate=self._target_rate,
                )
                self._send_chunk(pcm)

            except Exception as exc:
                log.warning("AudioStreamer software demod error: %s", exc, exc_info=True)
                self._stop_event.wait(timeout=1.0)
                continue

            # Pace the loop: target one chunk per _chunk_duration_s
            elapsed = time.monotonic() - t0
            wait = max(0.0, self._chunk_duration_s - elapsed)
            if wait > 0:
                self._stop_event.wait(timeout=wait)

        log.info("AudioStreamer: software mode stopped")

    # ── Internal ──────────────────────────────────────────────────────────────

    def _send_chunk(self, pcm: np.ndarray) -> None:
        """Encode PCM int16 to base64 and send via heartbeat WebSocket."""
        if len(pcm) == 0:
            return

        timestamp_ms = int(time.time() * 1000)
        pcm_bytes = pcm.astype("<i2").tobytes()   # ensure S16LE
        pcm_b64 = base64.b64encode(pcm_bytes).decode("ascii")

        self._heartbeat.send_audio_chunk(
            timestamp_ms=timestamp_ms,
            sample_rate=self._target_rate,
            channels=1,
            pcm_b64=pcm_b64,
        )
        log.debug(
            "AudioStreamer: sent %d samples (%.1f ms audio)",
            len(pcm), len(pcm) / self._target_rate * 1000,
        )

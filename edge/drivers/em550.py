"""
R&S EM550 VHF/UHF Wideband Monitoring Receiver — SCPI Driver
=============================================================
Manual reference: doc 4065.5119.32-06.00, Chapter 5 (Remote Control via LAN)

Hardware limits (verified from manual):
  Frequency range    : 20 MHz – 3.6 GHz
  PSCan step / RBW   : 125 | 250 | 500 | 625 | 1 250 | 2 500 | 3 125 | 6 250 |
                       12 500 | 25 000 | 50 000 | 100 000  Hz  (discrete)
  MTRACE max points  : 2 048 per sweep segment
  IFPAN span values  : 10 | 25 | 50 | 100 | 150 | 256 | 300 | 400 | 600 | 800 |
                       1 200 | 2 400 | 4 800 | 9 600  kHz  (discrete)
  IFPAN points       : always 2 049
  Level unit         : dBµV  →  driver converts to dBm  (50 Ω: dBm = dBµV − 107)

Connection:
  SCPI over raw TCP socket (no VISA installation required).
  Default port 5025.  Adjust if the device uses a different port
  (see Annex C: LAN Configuration in the manual).

Usage example:
    from edge.drivers.em550 import EM550Driver

    with EM550Driver(host="192.168.1.100") as rx:
        frame = rx.scan_range(
            start_hz=88e6, stop_hz=108e6, step_hz=25_000,
            station_id="site-01",
        )
        print(frame.levels_dbm)
"""
from __future__ import annotations

import logging
import math
import time
from typing import Optional

import numpy as np

from .base import BaseSpectrumDriver, SpectrumFrame

log = logging.getLogger(__name__)

# ── Hardware constants (from manual) ────────────────────────────────────────

_FREQ_MIN_HZ: float = 20e6       # 20 MHz
_FREQ_MAX_HZ: float = 3_600e6    # 3.6 GHz
_MTRACE_MAX_POINTS: int = 2_048  # max data points per single MTRACE read

# Valid PSCan step sizes in Hz (also determines RBW)
_PSCAN_VALID_STEPS_HZ: list[int] = [
    125, 250, 500, 625,
    1_250, 2_500, 3_125, 6_250,
    12_500, 25_000, 50_000, 100_000,
]

# Valid IF-panorama span values in Hz
_IFPAN_VALID_SPANS_HZ: list[int] = [
    10_000, 25_000, 50_000, 100_000, 150_000, 256_000,
    300_000, 400_000, 600_000, 800_000,
    1_200_000, 2_400_000, 4_800_000, 9_600_000,
]
_IFPAN_POINTS: int = 2_049  # always fixed (from manual)

# 50 Ω impedance: P = V²/R  →  0 dBµV = 1 µV → (1e-6)² / 50 = 2e-17 W = −107 dBm
_DBUV_TO_DBM: float = -107.0

# Marker value emitted by PSCan at range boundaries (INF)
_INF_MARKER: float = 9.9e37
_INF_THRESHOLD: float = _INF_MARKER * 0.9  # anything above this is treated as INF


# ── Helpers ──────────────────────────────────────────────────────────────────

def _nearest_pscan_step(requested_hz: float) -> int:
    """
    Return the nearest valid PSCan step (Hz) to requested_hz.
    Rounds up to keep resolution ≥ requested; caps at maximum.
    """
    for v in _PSCAN_VALID_STEPS_HZ:
        if v >= requested_hz:
            return v
    return _PSCAN_VALID_STEPS_HZ[-1]


def _nearest_ifpan_span(requested_hz: float) -> int:
    """Return the nearest valid IFPAN span (Hz) to requested_hz."""
    return min(_IFPAN_VALID_SPANS_HZ, key=lambda v: abs(v - requested_hz))


def _parse_ascii_floats(raw: str) -> np.ndarray:
    """Parse a comma-separated ASCII float string into a float32 array."""
    parts = raw.strip().split(",")
    return np.array([float(p) for p in parts if p.strip()], dtype=np.float32)


# ── Driver ───────────────────────────────────────────────────────────────────

class EM550Driver(BaseSpectrumDriver):
    """
    SCPI driver for the R&S EM550 VHF/UHF Wideband Monitoring Receiver.

    Parameters
    ----------
    host : str
        IP address or hostname of the EM550.
    port : int
        TCP port for SCPI socket (default 5025; verify in Annex C of manual).
    timeout_ms : int
        Socket / query timeout in milliseconds.
    default_step_hz : float
        Default PSCan step / RBW if scan_range() is called without step_hz.
    detector : str
        Level detector: "PAVerage" (default) | "POSitive" (peak) |
                        "FAST" (instantaneous) | "RMS"
    synth_mode : str
        Synthesiser mode affecting phase noise vs scan speed:
        "FAST" | "NORMal" | "LOWPnoise"
    dwell_s : float
        Per-step dwell time in seconds (PSCan mode).
    agc : bool
        True = automatic gain control (default).
        False = manual gain control; use mgc_dbuv to set the level.
    mgc_dbuv : float
        MGC value in dBµV (only used when agc=False).
        Range: −30 dBµV (max sensitivity) to 110 dBµV (min sensitivity).
    """

    def __init__(
        self,
        host: str,
        port: int = 5025,
        timeout_ms: int = 60_000,
        default_step_hz: float = 25_000,
        detector: str = "PAVerage",
        synth_mode: str = "FAST",
        dwell_s: float = 0.001,
        agc: bool = True,
        mgc_dbuv: float = 50.0,
    ) -> None:
        self._host = host
        self._port = port
        self._timeout_ms = timeout_ms
        self._default_step_hz = default_step_hz
        self._detector = detector
        self._synth_mode = synth_mode
        self._dwell_s = dwell_s
        self._agc = agc
        self._mgc_dbuv = mgc_dbuv

        self._instr = None  # RsInstrument instance, set in connect()

    # ── BaseSpectrumDriver properties ────────────────────────────────────

    @property
    def freq_min_hz(self) -> float:
        return _FREQ_MIN_HZ

    @property
    def freq_max_hz(self) -> float:
        return _FREQ_MAX_HZ

    @property
    def max_span_per_segment_hz(self) -> float:
        """Maximum single-segment span given current step setting."""
        step = _nearest_pscan_step(self._default_step_hz)
        return _MTRACE_MAX_POINTS * step

    # ── Connection ───────────────────────────────────────────────────────

    def connect(self) -> None:
        """
        Open SCPI connection to the EM550.

        Uses RsInstrument in pure-socket mode (no VISA required).
        Resource string format: TCPIP::<host>::<port>::SOCKET
        """
        try:
            from RsInstrument import RsInstrument
        except ImportError as e:
            raise ImportError(
                "RsInstrument package is required.  "
                "Install with: pip install RsInstrument"
            ) from e

        resource = f"TCPIP::{self._host}::{self._port}::SOCKET"
        log.info("Connecting to EM550 at %s", resource)

        self._instr = RsInstrument(
            resource_name=resource,
            id_query=False,   # EM550 IDN may differ from modern R&S format
            reset=False,      # do NOT auto-reset on connect; call reset() explicitly
            options=f"SelectVisa='SocketIo', OpenTimeout={self._timeout_ms}",
        )
        self._instr.visa_timeout = self._timeout_ms

        # Verify communication
        idn = self._instr.query_str("*IDN?")
        log.info("Connected: %s", idn.strip())

        self._apply_default_settings()

    def disconnect(self) -> None:
        if self._instr is not None:
            try:
                self._instr.close()
            except Exception:
                pass
            self._instr = None
            log.info("Disconnected from EM550 %s", self._host)

    # ── Public scan API ──────────────────────────────────────────────────

    def scan_range(
        self,
        start_hz: float,
        stop_hz: float,
        step_hz: Optional[float] = None,
        station_id: str = "",
        task_id: str = "",
    ) -> SpectrumFrame:
        """
        Sweep start_hz → stop_hz and return a stitched SpectrumFrame.

        The EM550 PSCan mode is limited to 2 048 points per acquisition.
        This method automatically splits the requested range into segments
        and concatenates the results transparently.

        Returns levels in dBm (converted from dBµV internally).
        """
        self._require_connected()

        step = _nearest_pscan_step(step_hz if step_hz is not None else self._default_step_hz)
        start_hz = max(start_hz, _FREQ_MIN_HZ)
        stop_hz = min(stop_hz, _FREQ_MAX_HZ)

        if step_hz is not None and step != step_hz:
            log.debug(
                "Requested step %.0f Hz rounded to nearest valid value %.0f Hz",
                step_hz, step,
            )

        segment_span = _MTRACE_MAX_POINTS * step  # max span per hardware sweep
        all_levels: list[np.ndarray] = []
        seg_start = start_hz

        log.debug(
            "PSCan %.3f–%.3f MHz, step=%.0f Hz, segment span=%.3f MHz",
            start_hz / 1e6, stop_hz / 1e6, step, segment_span / 1e6,
        )

        while seg_start < stop_hz:
            seg_stop = min(seg_start + segment_span, stop_hz)
            levels = self._pscan_segment(seg_start, seg_stop, step)
            all_levels.append(levels)
            # Advance to next segment; align to step boundary
            seg_start = seg_stop + step

        if not all_levels:
            raise RuntimeError("No scan data acquired — check frequency range")

        levels_dbuv = np.concatenate(all_levels).astype(np.float32)
        levels_dbm = levels_dbuv + _DBUV_TO_DBM

        return SpectrumFrame(
            station_id=station_id,
            timestamp_ms=SpectrumFrame.now_ms(),
            freq_start_hz=float(start_hz),
            freq_step_hz=float(step),
            levels_dbm=levels_dbm,
            task_id=task_id,
            driver="em550",
        )

    def scan_ifpan(
        self,
        center_hz: float,
        span_hz: float,
        station_id: str = "",
        task_id: str = "",
    ) -> SpectrumFrame:
        """
        IF-panorama scan centred on center_hz with the given span.

        Uses the IFPAN trace (software option EM550SU or EM550IM required).
        Always returns exactly 2 049 points.  Useful for detailed analysis
        of a narrow frequency band around a signal of interest.

        Args:
            center_hz : Centre frequency in Hz.
            span_hz   : IF panorama span in Hz (rounded to nearest valid value).
        """
        self._require_connected()
        span = _nearest_ifpan_span(span_hz)
        step = span / (_IFPAN_POINTS - 1)

        log.debug(
            "IFPAN centre=%.3f MHz span=%.0f kHz (%d points)",
            center_hz / 1e6, span / 1e3, _IFPAN_POINTS,
        )

        w = self._instr.write
        q = self._instr.query_str

        w(f"SENSe:FREQuency:MODE CW")
        w(f"SENSe:FREQuency {center_hz:.0f}")
        w(f"SENSe:FREQuency:SPAN {span:.0f}")
        w("TRACe:FEED:CONTrol IFPAN, ALWays")
        w("DISPlay:MENU IFPAN")

        # Trigger one acquisition
        w("ABORt")
        w("INITiate:IMMediate")
        self._wait_sweep_complete()

        raw = q("TRACe? IFPAN")
        levels_dbuv = _parse_ascii_floats(raw)

        # IFPAN always returns 2049 points; trim to be safe
        levels_dbuv = levels_dbuv[:_IFPAN_POINTS]
        levels_dbm = (levels_dbuv + _DBUV_TO_DBM).astype(np.float32)

        start_hz = center_hz - span / 2.0
        return SpectrumFrame(
            station_id=station_id,
            timestamp_ms=SpectrumFrame.now_ms(),
            freq_start_hz=float(start_hz),
            freq_step_hz=float(step),
            levels_dbm=levels_dbm,
            task_id=task_id,
            driver="em550-ifpan",
        )

    # ── Utility / setup ──────────────────────────────────────────────────

    def reset(self) -> None:
        """Send *RST and re-apply driver defaults."""
        self._require_connected()
        self._instr.write("*RST")
        self._instr.write("*CLS")
        self._instr.query_str("*OPC?")  # wait for reset to complete
        self._apply_default_settings()
        log.info("EM550 reset complete")

    def set_detector(self, detector: str) -> None:
        """
        Change the level detector.
        detector: "PAVerage" | "POSitive" | "FAST" | "RMS"
        """
        self._require_connected()
        self._detector = detector
        self._instr.write(f"SENSe:DETector {detector}")

    def set_agc(self, enabled: bool, mgc_dbuv: float = 50.0) -> None:
        """Enable or disable automatic gain control."""
        self._require_connected()
        self._agc = enabled
        self._mgc_dbuv = mgc_dbuv
        if enabled:
            self._instr.write("SENSe:GCONtrol:MODE AUTO")
        else:
            self._instr.write("SENSe:GCONtrol:MODE FIXed")
            self._instr.write(f"SENSe:GCONtrol {mgc_dbuv:.1f}")

    def query_level(self, freq_hz: float) -> float:
        """
        Quick single-frequency level measurement in dBm.
        Switches to CW mode, measures, returns to PSCan mode.
        """
        self._require_connected()
        w = self._instr.write
        q = self._instr.query_str

        w(f"SENSe:FREQuency:MODE CW")
        w(f"SENSe:FREQuency {freq_hz:.0f}")
        w("SENSe:FUNCtion \"VOLT:AC\"")
        w("TRACe:FEED:CONTrol MTRACE, ALWays")
        w("INITiate:IMMediate")
        self._wait_sweep_complete()

        raw = q("SENSe:DATA? \"VOLT:AC\"")
        level_dbuv = float(raw.strip())
        return level_dbuv + _DBUV_TO_DBM

    # ── Internal helpers ─────────────────────────────────────────────────

    def _apply_default_settings(self) -> None:
        """Apply the driver's default configuration to the instrument."""
        w = self._instr.write

        # Use ASCII data format (PACKED binary is faster but adds complexity)
        w("FORMat:DATA ASCii")

        # Detector
        w(f"SENSe:DETector {self._detector}")

        # Synthesiser speed
        w(f"SENSe:FREQuency:SYNThesizer:MODE {self._synth_mode}")

        # Gain control
        if self._agc:
            w("SENSe:GCONtrol:MODE AUTO")
        else:
            w("SENSe:GCONtrol:MODE FIXed")
            w(f"SENSe:GCONtrol {self._mgc_dbuv:.1f}")

        # Enable level measurement function
        w("SENSe:FUNCtion \"VOLT:AC\"")

        log.debug(
            "EM550 defaults applied: detector=%s synth=%s agc=%s",
            self._detector, self._synth_mode, self._agc,
        )

    def _pscan_segment(
        self,
        seg_start_hz: float,
        seg_stop_hz: float,
        step_hz: int,
    ) -> np.ndarray:
        """
        Execute one PSCan hardware sweep over [seg_start_hz, seg_stop_hz]
        and return a float32 array of level values in dBµV.

        The EM550 appends an INF marker (9.9E37) at the end of each range;
        this method strips it before returning.
        """
        w = self._instr.write
        q = self._instr.query_str

        expected_points = math.ceil((seg_stop_hz - seg_start_hz) / step_hz) + 1

        log.debug(
            "  segment %.3f–%.3f MHz (~%d points)",
            seg_start_hz / 1e6, seg_stop_hz / 1e6, expected_points,
        )

        # Configure PSCan mode
        w("SENSe:FREQuency:MODE PSCan")
        w(f"SENSe:FREQuency:PSCan:STARt {seg_start_hz:.0f}")
        w(f"SENSe:FREQuency:PSCan:STOP {seg_stop_hz:.0f}")
        w(f"SENSe:PSCan:STEP {step_hz:.0f}")
        w(f"SENSe:PSCan:COUNt 1")                      # single sweep
        w(f"SENSe:PSCan:DWELl {self._dwell_s:.6f}")    # NOTE: PSCan uses SWEep:DWELl syntax

        # Enable MTRACE capture
        w("TRACe:FEED:CONTrol MTRACE, ALWays")

        # Trigger sweep
        w("ABORt")                    # abort any in-progress sweep
        w("INITiate:IMMediate")       # start new sweep

        self._wait_sweep_complete()

        raw = q("TRACe? MTRACE")
        if not raw or not raw.strip():
            log.warning("Empty MTRACE response for segment %.3f–%.3f MHz",
                        seg_start_hz / 1e6, seg_stop_hz / 1e6)
            return np.full(expected_points, np.nan, dtype=np.float32)

        levels = _parse_ascii_floats(raw)

        # Strip INF range-boundary markers (value ≥ _INF_THRESHOLD)
        valid_mask = levels < _INF_THRESHOLD
        levels = levels[valid_mask]

        if len(levels) == 0:
            log.warning("All MTRACE values were INF for segment %.3f–%.3f MHz",
                        seg_start_hz / 1e6, seg_stop_hz / 1e6)
            return np.full(expected_points, np.nan, dtype=np.float32)

        # Trim or pad to expected length (defensive)
        if len(levels) > expected_points:
            levels = levels[:expected_points]
        elif len(levels) < expected_points:
            pad = np.full(expected_points - len(levels), np.nan, dtype=np.float32)
            levels = np.concatenate([levels, pad])

        return levels.astype(np.float32)

    def _wait_sweep_complete(self, poll_interval_s: float = 0.05) -> None:
        """
        Block until the current sweep / measurement is finished.

        Strategy: poll *OPC? (Operation Complete query).  After INITiate,
        the instrument sets the OPC bit in the Event Status Register when
        the operation is done.  *OPC? blocks until that bit is set.

        Timeout is derived from self._timeout_ms.
        """
        deadline = time.monotonic() + self._timeout_ms / 1000.0
        try:
            # *OPC? returns "1" when the current operation is complete.
            # RsInstrument will honour the VISA timeout set in connect().
            result = self._instr.query_str("*OPC?")
            if result.strip() != "1":
                log.warning("*OPC? returned unexpected value: %r", result)
        except Exception as exc:
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"EM550 sweep did not complete within {self._timeout_ms} ms"
                ) from exc
            raise

    def _require_connected(self) -> None:
        if self._instr is None:
            raise RuntimeError(
                "Not connected.  Call connect() first, "
                "or use the driver as a context manager."
            )

    # ── Repr ────────────────────────────────────────────────────────────

    def __repr__(self) -> str:
        status = "connected" if self._instr else "disconnected"
        return (
            f"EM550Driver(host={self._host!r}, port={self._port}, "
            f"step={self._default_step_hz:.0f} Hz, {status})"
        )

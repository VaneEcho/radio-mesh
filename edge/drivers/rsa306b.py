"""
Tektronix RSA306B USB Spectrum Analyzer — Driver
=================================================
Uses the ``rsa_api`` package (installed via ``pip install tekrsa-api-wrap``),
which wraps the Tektronix RSA API for Linux via ctypes.

Hardware limits:
  Frequency range : 9 kHz – 6.2 GHz
  Max real-time BW: 40 MHz per acquisition
  Interface       : USB 3.0
  Library         : tekrsa-api-wrap >= 2.0  (module name: rsa_api)

Native library requirement:
  The rsa_api Python package is a ctypes wrapper — it requires the proprietary
  Tektronix RSA API shared libraries to be installed on the system:
    libRSA_API.so
    libcyusb_shared.so
  These ship with Tektronix SignalVu-PC or the standalone RSA API for Linux
  package.  By default ``rsa_api.RSA()`` looks for them in ``/drivers/``; set
  ``so_dir`` in config.yaml to override.

Scan strategy (band_scan):
  The RSA306B captures up to 40 MHz per real-time FFT acquisition.  For wider
  scans the driver steps in 40 MHz increments and stitches into one
  SpectrumFrame.  All segments use the full 40 MHz span so that freq_step_hz
  is uniform throughout (= 40 MHz / (trace_length − 1) ≈ 50 kHz at 801 pts).
"""
from __future__ import annotations

import logging
import math
import time

import numpy as np

from .base import BaseSpectrumDriver, SpectrumFrame

log = logging.getLogger(__name__)

# Hardware constants
_FREQ_MIN_HZ: float = 9e3
_FREQ_MAX_HZ: float = 6_200e6
_MAX_BW_HZ:   float = 40e6        # max real-time BW per acquisition
_DEFAULT_RBW_HZ:    float = 10_000
_DEFAULT_TRACE_LEN: int   = 801
_WAIT_TIMEOUT_MS:   int   = 5_000  # data-ready timeout in ms

# Default so_dir expected by rsa_api.RSA()
_DEFAULT_SO_DIR: str = "/drivers/"


class RSA306BDriver(BaseSpectrumDriver):
    """
    Driver for the Tektronix RSA306B USB spectrum analyser.

    Parameters
    ----------
    device_index : int
        USB device index (0-based, default 0).
    rbw_hz : float
        Resolution bandwidth per segment in Hz (default 10 kHz).
    trace_length : int
        Spectrum points per 40-MHz segment (default 801).
    ref_level_dbm : float
        Reference level in dBm (default 0.0).
    so_dir : str
        Directory containing libRSA_API.so and libcyusb_shared.so.
        Defaults to ``/drivers/`` (rsa_api package default).
    """

    def __init__(
        self,
        device_index: int = 0,
        rbw_hz: float = _DEFAULT_RBW_HZ,
        trace_length: int = _DEFAULT_TRACE_LEN,
        ref_level_dbm: float = 0.0,
        so_dir: str = _DEFAULT_SO_DIR,
    ) -> None:
        self._dev_idx      = device_index
        self._rbw_hz       = rbw_hz
        self._trace_length = trace_length
        self._ref_level_dbm = ref_level_dbm
        self._so_dir       = so_dir
        self._rsa          = None  # rsa_api.RSA instance, set in connect()

    # ── BaseSpectrumDriver properties ─────────────────────────────────────────

    @property
    def freq_min_hz(self) -> float:
        return _FREQ_MIN_HZ

    @property
    def freq_max_hz(self) -> float:
        return _FREQ_MAX_HZ

    @property
    def max_span_per_segment_hz(self) -> float:
        return _MAX_BW_HZ

    # ── Connection lifecycle ──────────────────────────────────────────────────

    def connect(self) -> None:
        """
        Open the USB connection to the RSA306B.

        Requires ``tekrsa-api-wrap`` (pip install tekrsa-api-wrap) and the
        Tektronix RSA API native libraries (libRSA_API.so + libcyusb_shared.so)
        in ``so_dir``.
        """
        try:
            import rsa_api
        except ImportError as exc:
            raise ImportError(
                "tekrsa-api-wrap is required for RSA306B.  "
                "Install with: pip install tekrsa-api-wrap"
            ) from exc

        log.info("Loading RSA API libraries from %s", self._so_dir)
        try:
            rsa = rsa_api.RSA(so_dir=self._so_dir)
        except OSError as exc:
            raise RuntimeError(
                f"Failed to load RSA API native libraries from '{self._so_dir}': {exc}\n"
                "Ensure libRSA_API.so and libcyusb_shared.so are present "
                "and the device driver (libcyusb) is installed."
            ) from exc

        log.info("Searching for RSA306B devices via USB …")
        try:
            found = rsa.DEVICE_Search()
        except rsa_api.RSAError as exc:
            raise RuntimeError(f"No RSA306B devices found via USB: {exc}") from exc

        log.info("Found RSA device(s): %s", found)
        if self._dev_idx not in found:
            raise RuntimeError(
                f"device_index={self._dev_idx} not in found devices {list(found.keys())}"
            )

        rsa.DEVICE_Connect(self._dev_idx)
        log.info("Connected to RSA306B device index %d", self._dev_idx)

        rsa.CONFIG_SetReferenceLevel(self._ref_level_dbm)
        rsa.SPECTRUM_SetEnable(True)

        self._rsa = rsa

    def disconnect(self) -> None:
        if self._rsa is not None:
            try:
                self._rsa.DEVICE_Stop()
                self._rsa.DEVICE_Disconnect()
                log.info("Disconnected from RSA306B")
            except Exception:
                pass
            self._rsa = None

    # ── Scan operations ───────────────────────────────────────────────────────

    def band_scan(
        self,
        start_hz: float,
        stop_hz: float,
        step_hz: float = _DEFAULT_RBW_HZ,
        station_id: str = "",
        task_id: str = "",
    ) -> SpectrumFrame:
        """
        Wideband panoramic sweep start_hz → stop_hz.

        Segments the range into 40 MHz blocks acquired via real-time FFT, then
        stitches into one SpectrumFrame.  All segments use the full 40 MHz span
        so freq_step_hz is uniform:

            freq_step = 40 MHz / (trace_length − 1)   # ≈ 50 kHz at 801 pts

        ``step_hz`` is accepted for interface compatibility but is not used —
        RBW is controlled by the ``rbw_hz`` constructor parameter.
        """
        self._require_connected()

        start_hz = max(start_hz, _FREQ_MIN_HZ)
        stop_hz  = min(stop_hz,  _FREQ_MAX_HZ)

        seg_span = _MAX_BW_HZ
        seg_step = seg_span / (self._trace_length - 1)  # e.g. 50 kHz at 801 pts

        log.debug(
            "RSA306B band_scan %.3f–%.3f MHz, seg_span=%.0f MHz, "
            "seg_step=%.0f Hz, trace_length=%d",
            start_hz / 1e6, stop_hz / 1e6, seg_span / 1e6,
            seg_step, self._trace_length,
        )

        all_levels: list[np.ndarray] = []
        seg_start = start_hz
        while seg_start < stop_hz:
            center = seg_start + seg_span / 2.0
            levels = self._acquire_segment(center, seg_span, self._rbw_hz)
            all_levels.append(levels)
            seg_start += seg_span

        if not all_levels:
            raise RuntimeError("No data acquired from RSA306B")

        concatenated = np.concatenate(all_levels).astype(np.float32)

        # Discard points beyond stop_hz (last segment extends past it)
        n_pts = math.ceil((stop_hz - start_hz) / seg_step) + 1
        n_pts = max(1, min(n_pts, len(concatenated)))
        concatenated = concatenated[:n_pts]

        return SpectrumFrame(
            station_id=station_id,
            timestamp_ms=SpectrumFrame.now_ms(),
            freq_start_hz=float(start_hz),
            freq_step_hz=float(seg_step),
            levels_dbm=concatenated,
            task_id=task_id,
            driver="rsa306b",
        )

    def if_analysis(
        self,
        center_hz: float,
        span_hz: float,
        station_id: str = "",
        task_id: str = "",
    ) -> SpectrumFrame:
        """
        Narrow-band acquisition centred on center_hz with the given span.
        Span is clipped to 40 MHz maximum.
        """
        self._require_connected()
        span_hz  = min(span_hz, _MAX_BW_HZ)
        levels   = self._acquire_segment(center_hz, span_hz, self._rbw_hz)
        freq_step = span_hz / max(len(levels) - 1, 1)

        return SpectrumFrame(
            station_id=station_id,
            timestamp_ms=SpectrumFrame.now_ms(),
            freq_start_hz=float(center_hz - span_hz / 2.0),
            freq_step_hz=float(freq_step),
            levels_dbm=levels.astype(np.float32),
            task_id=task_id,
            driver="rsa306b-if",
        )

    def channel_scan(
        self,
        start_hz: float,
        stop_hz: float,
        step_hz: float,
        demod_bw_hz: float,
        station_id: str = "",
        task_id: str = "",
    ) -> SpectrumFrame:
        """
        Step through channels from start_hz to stop_hz in step_hz increments.
        Each channel is acquired with a span of demod_bw_hz.
        """
        self._require_connected()

        start_hz   = max(start_hz,   _FREQ_MIN_HZ)
        stop_hz    = min(stop_hz,    _FREQ_MAX_HZ)
        span_hz    = min(demod_bw_hz, _MAX_BW_HZ)

        channel_levels: list[float] = []
        ch_hz = start_hz
        while ch_hz <= stop_hz:
            levels = self._acquire_segment(ch_hz, span_hz, self._rbw_hz)
            mid = len(levels) // 2
            channel_levels.append(float(levels[mid]))
            ch_hz += step_hz

        arr = np.array(channel_levels, dtype=np.float32)
        return SpectrumFrame(
            station_id=station_id,
            timestamp_ms=SpectrumFrame.now_ms(),
            freq_start_hz=float(start_hz),
            freq_step_hz=float(step_hz),
            levels_dbm=arr,
            task_id=task_id,
            driver="rsa306b-ch",
        )

    def if_analysis_iq(
        self,
        center_hz: float,
        span_hz: float,
        duration_s: float = 0.1,
        station_id: str = "",
        task_id: str = "",
    ) -> tuple["SpectrumFrame", np.ndarray, float]:
        """
        Narrow-band IQ capture centred on center_hz.

        Returns (SpectrumFrame, iq_complex64, sample_rate_hz).
        """
        self._require_connected()
        rsa = self._rsa
        span_hz = min(span_hz, _MAX_BW_HZ)

        sample_rate   = span_hz
        record_length = max(1, int(sample_rate * duration_s))

        rsa.CONFIG_SetCenterFreq(float(center_hz))
        rsa.CONFIG_SetReferenceLevel(self._ref_level_dbm)
        rsa.IQBLK_SetIQBandwidth(float(span_hz))
        rsa.IQBLK_SetIQRecordLength(record_length)

        rsa.DEVICE_Run()
        rsa.IQBLK_AcquireIQData()

        ready = rsa.IQBLK_WaitForIQDataReady(_WAIT_TIMEOUT_MS)
        if not ready:
            log.warning(
                "RSA306B: IQ data not ready after %d ms for centre=%.3f MHz",
                _WAIT_TIMEOUT_MS, center_hz / 1e6,
            )
            empty_frame = SpectrumFrame(
                station_id=station_id,
                timestamp_ms=SpectrumFrame.now_ms(),
                freq_start_hz=float(center_hz - span_hz / 2),
                freq_step_hz=float(span_hz / self._trace_length),
                levels_dbm=np.full(self._trace_length, np.nan, dtype=np.float32),
                task_id=task_id,
                driver="rsa306b-iq",
            )
            rsa.DEVICE_Stop()
            return empty_frame, np.array([], dtype=np.complex64), float(sample_rate)

        # IQBLK_GetIQData returns interleaved I/Q float32 ndarray directly
        iq_flat = rsa.IQBLK_GetIQData(record_length).astype(np.float32)
        rsa.DEVICE_Stop()

        iq_complex = (iq_flat[0::2] + 1j * iq_flat[1::2]).astype(np.complex64)

        if len(iq_complex) > 0:
            fft      = np.fft.fftshift(np.fft.fft(iq_complex, n=self._trace_length))
            power_db = (20 * np.log10(np.abs(fft) / len(fft) + 1e-12)
                        + float(self._ref_level_dbm)).astype(np.float32)
        else:
            power_db = np.full(self._trace_length, np.nan, dtype=np.float32)

        freq_step = span_hz / max(len(power_db) - 1, 1)
        spectrum  = SpectrumFrame(
            station_id=station_id,
            timestamp_ms=SpectrumFrame.now_ms(),
            freq_start_hz=float(center_hz - span_hz / 2),
            freq_step_hz=float(freq_step),
            levels_dbm=power_db,
            task_id=task_id,
            driver="rsa306b-iq",
        )

        actual_sample_rate_hz = float(rsa.IQBLK_GetIQBandwidth())
        return spectrum, iq_complex, actual_sample_rate_hz

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _acquire_segment(
        self,
        center_hz: float,
        span_hz: float,
        rbw_hz: float,
    ) -> np.ndarray:
        """
        One spectrum acquisition centred on center_hz.
        Returns float32 array of power levels in dBm.
        """
        rsa = self._rsa

        rsa.CONFIG_SetCenterFreq(float(center_hz))
        rsa.CONFIG_SetReferenceLevel(self._ref_level_dbm)

        rsa.SPECTRUM_SetSettings(
            span=float(span_hz),
            rbw=float(rbw_hz),
            enable_vbw=False,
            vbw=float(rbw_hz),   # ignored when enable_vbw=False
            trace_len=self._trace_length,
            win="Kaiser",
            vert_unit="dBm",
        )

        rsa.DEVICE_Run()
        rsa.SPECTRUM_AcquireTrace()

        ready = rsa.SPECTRUM_WaitForTraceReady(_WAIT_TIMEOUT_MS)
        if not ready:
            log.warning(
                "RSA306B: data not ready after %d ms for centre=%.3f MHz",
                _WAIT_TIMEOUT_MS, center_hz / 1e6,
            )
            rsa.DEVICE_Stop()
            return np.full(self._trace_length, np.nan, dtype=np.float32)

        trace_data, out_len = rsa.SPECTRUM_GetTrace("Trace1", self._trace_length)
        rsa.DEVICE_Stop()

        levels = np.array(trace_data[:out_len], dtype=np.float32)
        log.debug(
            "RSA306B segment: centre=%.3f MHz span=%.1f MHz → %d pts",
            center_hz / 1e6, span_hz / 1e6, len(levels),
        )
        return levels

    def _require_connected(self) -> None:
        if self._rsa is None:
            raise RuntimeError(
                "RSA306B not connected.  Call connect() first, "
                "or use the driver as a context manager."
            )

    def __repr__(self) -> str:
        status = "connected" if self._rsa else "disconnected"
        return (
            f"RSA306BDriver(device_index={self._dev_idx}, "
            f"rbw={self._rbw_hz:.0f} Hz, {status})"
        )

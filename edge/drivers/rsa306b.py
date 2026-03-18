"""
Tektronix RSA306B USB Spectrum Analyzer — Driver
=================================================
Implements BaseSpectrumDriver using the tekrsa-api-wrap package, which wraps
the Tektronix RSA C API (libRSA_API.so on Linux, RSA_API.dll on Windows).

Hardware limits:
  Frequency range : 9 kHz – 6.2 GHz
  Max real-time BW: 40 MHz per acquisition
  Interface       : USB 3.0
  Library         : tekrsa-api-wrap  (pip install tekrsa-api-wrap)
  Reference       : https://github.com/NTIA/tekrsa-api-wrap

Scan strategy (band_scan):
  The RSA306B captures a contiguous 40 MHz block per acquisition.  For wider
  scans the driver steps the centre frequency in 40 MHz increments and stitches
  the result into one SpectrumFrame — identical strategy to the EM550 driver.

Install dependencies (not bundled in requirements.txt because tekrsa-api-wrap
requires the proprietary RSA_API shared library to be installed separately):
    pip install tekrsa-api-wrap

Usage:
    from edge.drivers.rsa306b import RSA306BDriver

    with RSA306BDriver(device_index=0, rbw_hz=10_000) as rx:
        frame = rx.band_scan(
            start_hz=400e6, stop_hz=500e6,
            station_id="site-02",
        )
"""
from __future__ import annotations

import logging
import math
import time

import numpy as np

from .base import BaseSpectrumDriver, SpectrumFrame

log = logging.getLogger(__name__)

# Hardware constants
_FREQ_MIN_HZ: float = 9e3         # 9 kHz
_FREQ_MAX_HZ: float = 6_200e6    # 6.2 GHz
_MAX_BW_HZ: float = 40e6         # 40 MHz max real-time BW per acquisition
_DEFAULT_RBW_HZ: float = 10_000  # 10 kHz default RBW
_DEFAULT_TRACE_LEN: int = 801    # default number of trace points
_WAIT_TIMEOUT_MS: int = 5_000    # data-ready timeout in ms

# Trace type constants (from RSA API)
_TRACE_TYPE_MAX_HOLD = 0
_TRACE_TYPE_MIN_HOLD = 1
_TRACE_TYPE_AVERAGE  = 2

# Vertical unit constants
_VERT_UNIT_DBM = 0


class RSA306BDriver(BaseSpectrumDriver):
    """
    Driver for the Tektronix RSA306B USB spectrum analyser.

    Parameters
    ----------
    device_index : int
        USB device index to connect to (0-based, default 0).
    rbw_hz : float
        Resolution bandwidth in Hz (default 10 kHz).
    trace_length : int
        Number of trace points per acquisition segment (default 801).
    ref_level_dbm : float
        Reference level in dBm (default 0.0).  Reduce if you see clipping;
        increase if you see noise floor artefacts.
    """

    FREQ_MIN_HZ: float = _FREQ_MIN_HZ
    FREQ_MAX_HZ: float = _FREQ_MAX_HZ
    MAX_REALTIME_BW_HZ: float = _MAX_BW_HZ

    def __init__(
        self,
        device_index: int = 0,
        rbw_hz: float = _DEFAULT_RBW_HZ,
        trace_length: int = _DEFAULT_TRACE_LEN,
        ref_level_dbm: float = 0.0,
    ) -> None:
        self._dev_idx = device_index
        self._rbw_hz = rbw_hz
        self._trace_length = trace_length
        self._ref_level_dbm = ref_level_dbm
        self._rsa = None  # tekrsa_api_wrap module, set in connect()

    # ── BaseSpectrumDriver properties ────────────────────────────────────────

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

        Requires tekrsa-api-wrap and the RSA_API shared library.
        On Linux: export RSA_API_LIB=/path/to/libRSA_API.so before running.
        """
        try:
            import tekrsa_api_wrap as rsa
        except ImportError as exc:
            raise ImportError(
                "tekrsa-api-wrap is required for RSA306B.  "
                "Install with: pip install tekrsa-api-wrap"
            ) from exc

        self._rsa = rsa

        num_found, dev_ids, _ = rsa.DEVICE_Search()
        if num_found == 0:
            raise RuntimeError("No RSA306B devices found via USB")

        log.info("Found %d RSA device(s): %s", num_found, dev_ids)
        if self._dev_idx >= num_found:
            raise RuntimeError(
                f"device_index={self._dev_idx} out of range "
                f"(found {num_found} device(s))"
            )

        rsa.DEVICE_Connect(self._dev_idx)
        log.info("Connected to RSA306B device index %d", self._dev_idx)

        # Apply initial settings
        rsa.CONFIG_SetReferenceLevel(self._ref_level_dbm)
        rsa.SPECTRUM_SetEnable(True)

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

        Segments the range into ≤40 MHz chunks, acquires each, then stitches
        into one SpectrumFrame.  `step_hz` is used as a guide for RBW; the
        actual frequency step within each segment is:
            freq_step = span / (trace_length - 1)
        """
        self._require_connected()

        start_hz = max(start_hz, _FREQ_MIN_HZ)
        stop_hz = min(stop_hz, _FREQ_MAX_HZ)

        all_levels: list[np.ndarray] = []
        all_starts: list[float] = []
        seg_center = start_hz + _MAX_BW_HZ / 2.0

        while seg_center - _MAX_BW_HZ / 2.0 < stop_hz:
            seg_start = seg_center - _MAX_BW_HZ / 2.0
            seg_stop = seg_center + _MAX_BW_HZ / 2.0

            # Clip the last segment so we don't go past stop_hz
            actual_span = min(_MAX_BW_HZ, stop_hz - seg_start)
            if actual_span <= 0:
                break

            # Use actual_span / trace_length for this segment's step
            actual_center = seg_start + actual_span / 2.0
            levels = self._acquire_segment(actual_center, actual_span, self._rbw_hz)
            all_levels.append(levels)
            all_starts.append(seg_start)

            seg_center += _MAX_BW_HZ

        if not all_levels:
            raise RuntimeError("No data acquired from RSA306B")

        concatenated = np.concatenate(all_levels).astype(np.float32)
        # Compute uniform step across the full stitched range
        total_range = stop_hz - start_hz
        freq_step = total_range / max(len(concatenated) - 1, 1)

        return SpectrumFrame(
            station_id=station_id,
            timestamp_ms=SpectrumFrame.now_ms(),
            freq_start_hz=float(start_hz),
            freq_step_hz=float(freq_step),
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
        span_hz = min(span_hz, _MAX_BW_HZ)
        levels = self._acquire_segment(center_hz, span_hz, self._rbw_hz)
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
        The results are concatenated into a single SpectrumFrame.
        """
        self._require_connected()

        start_hz = max(start_hz, _FREQ_MIN_HZ)
        stop_hz = min(stop_hz, _FREQ_MAX_HZ)
        span_hz = min(demod_bw_hz, _MAX_BW_HZ)

        channel_levels: list[float] = []
        ch_hz = start_hz
        while ch_hz <= stop_hz:
            levels = self._acquire_segment(ch_hz, span_hz, self._rbw_hz)
            # Take the centre bin as the channel's representative level
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

        Returns a tuple of:
          - ``SpectrumFrame``  — spectrum (power vs frequency) for display
          - ``iq_samples``     — complex64 numpy array of baseband IQ samples
          - ``sample_rate_hz`` — IQ sample rate in Hz

        The IQ samples can be passed directly to ``edge.demod.demodulate()``
        for software AM/FM/SSB demodulation.

        Parameters
        ----------
        center_hz:  Centre frequency in Hz.
        span_hz:    Capture bandwidth in Hz (clipped to 40 MHz max).
        duration_s: IQ capture duration in seconds (default 0.1 s = 100 ms).
        """
        self._require_connected()
        rsa = self._rsa
        span_hz = min(span_hz, _MAX_BW_HZ)

        sample_rate = span_hz  # RSA306B: IQ sample rate == span in Hz (approx)
        record_length = max(1, int(sample_rate * duration_s))

        log.debug(
            "RSA306B IQ capture: centre=%.3f MHz span=%.1f kHz "
            "dur=%.3f s → %d samples",
            center_hz / 1e6, span_hz / 1e3, duration_s, record_length,
        )

        rsa.CONFIG_SetCenterFreq(float(center_hz))
        rsa.CONFIG_SetReferenceLevel(self._ref_level_dbm)

        # Configure IQ block acquisition
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
            # Return empty arrays
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

        # Retrieve IQ samples (interleaved I/Q float32)
        iq_data, actual_len = rsa.IQBLK_GetIQData(record_length)
        rsa.DEVICE_Stop()

        # Convert to complex64 array
        iq_flat = np.array(iq_data[:actual_len * 2], dtype=np.float32)
        iq_complex = iq_flat[0::2] + 1j * iq_flat[1::2]
        iq_complex = iq_complex.astype(np.complex64)

        # Also compute spectrum from this IQ block (magnitude²)
        if len(iq_complex) > 0:
            fft = np.fft.fftshift(np.fft.fft(iq_complex, n=self._trace_length))
            power_db = 20 * np.log10(np.abs(fft) / len(fft) + 1e-12)
            # Shift by reference level approximation
            power_db = power_db.astype(np.float32) + float(self._ref_level_dbm)
        else:
            power_db = np.full(self._trace_length, np.nan, dtype=np.float32)

        freq_step = span_hz / max(len(power_db) - 1, 1)
        spectrum = SpectrumFrame(
            station_id=station_id,
            timestamp_ms=SpectrumFrame.now_ms(),
            freq_start_hz=float(center_hz - span_hz / 2),
            freq_step_hz=float(freq_step),
            levels_dbm=power_db,
            task_id=task_id,
            driver="rsa306b-iq",
        )

        # Actual IQ sample rate from the device (may differ slightly from span)
        actual_sample_rate_hz = float(rsa.IQBLK_GetIQBandwidth())

        log.debug(
            "RSA306B IQ: got %d complex samples at %.1f kHz sr",
            len(iq_complex), actual_sample_rate_hz / 1e3,
        )
        return spectrum, iq_complex, actual_sample_rate_hz

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _acquire_segment(
        self,
        center_hz: float,
        span_hz: float,
        rbw_hz: float,
    ) -> np.ndarray:
        """
        Perform one spectrum acquisition centred on center_hz.

        Returns float32 array of power levels in dBm.
        """
        rsa = self._rsa

        rsa.CONFIG_SetCenterFreq(float(center_hz))
        rsa.CONFIG_SetReferenceLevel(self._ref_level_dbm)

        # Configure spectrum settings
        settings = rsa.SPECTRUM_GetSettings()
        settings.span = float(span_hz)
        settings.rbw = float(rbw_hz)
        settings.traceLength = self._trace_length
        settings.verticalUnit = _VERT_UNIT_DBM
        rsa.SPECTRUM_SetSettings(settings)

        # Acquire
        rsa.DEVICE_Run()
        rsa.SPECTRUM_AcquireTrace()

        ready = rsa.SPECTRUM_WaitForDataReady(_WAIT_TIMEOUT_MS)
        if not ready:
            log.warning(
                "RSA306B: data not ready after %d ms for centre=%.3f MHz",
                _WAIT_TIMEOUT_MS, center_hz / 1e6,
            )
            actual_len = settings.traceLength
            return np.full(actual_len, np.nan, dtype=np.float32)

        trace_data, out_len = rsa.SPECTRUM_GetTrace(
            _TRACE_TYPE_MAX_HOLD, self._trace_length
        )
        rsa.DEVICE_Stop()

        levels = np.array(trace_data[:out_len], dtype=np.float32)
        log.debug(
            "RSA306B segment: centre=%.3f MHz span=%.1f MHz → %d points",
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

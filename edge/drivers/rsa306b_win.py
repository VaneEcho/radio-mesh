"""
Tektronix RSA306B USB Spectrum Analyzer — Windows Driver
=========================================================
Uses ctypes to call RSA_API.dll directly (no tekrsa-api-wrap dependency).
Requires the Tektronix RSA API for Windows, shipped with SignalVu-PC or the
standalone RSA API installer from tek.com.

Hardware limits:
  Frequency range : 9 kHz – 6.2 GHz
  Max real-time BW: 40 MHz per acquisition
  Interface       : USB 3.0

DLL location (default):
  C:\\Program Files\\Tektronix\\RSA_API\\lib\\x64\\RSA_API.dll
  Override with ``dll_path`` in config.yaml.

Scan strategy: identical to the Linux driver — 40 MHz segments stitched into
one SpectrumFrame.
"""
from __future__ import annotations

import logging
import math
from ctypes import (
    CDLL, Structure, POINTER,
    c_int, c_double, c_float, c_bool, c_char, c_char_p,
    byref,
)

import numpy as np

from .base import BaseSpectrumDriver, SpectrumFrame

log = logging.getLogger(__name__)

# ── Hardware constants ─────────────────────────────────────────────────────────
_FREQ_MIN_HZ: float = 9e3
_FREQ_MAX_HZ: float = 6_200e6
_MAX_BW_HZ:   float = 40e6
_DEFAULT_RBW_HZ:    float = 10_000
_DEFAULT_TRACE_LEN: int   = 801
_WAIT_TIMEOUT_MS:   int   = 5_000

# ── API constants (enum values from RSA_API.h) ─────────────────────────────────
_NO_ERROR          = 0
_WINDOW_KAISER     = 0   # SpectrumWindow_Kaiser
_VERT_UNIT_DBM     = 0   # SpectrumVerticalUnit_dBm
_TRACE1            = 0   # SpectrumTrace1

# Search buffers
_DEVSRCH_MAX_NUM_DEVICES  = 20
_DEVSRCH_SERIAL_MAX_STRLEN = 100
_DEVSRCH_TYPE_MAX_STRLEN  = 20

# Default DLL path (SignalVu-PC installation)
_DEFAULT_DLL_PATH = r"C:\Program Files\Tektronix\RSA_API\lib\x64\RSA_API.dll"


# ── Structs ────────────────────────────────────────────────────────────────────

class _SpectrumSettings(Structure):
    """Maps to Spectrum_Settings in RSA_API.h."""
    _fields_ = [
        ("span",               c_double),
        ("rbw",                c_double),
        ("enableVBW",          c_bool),
        ("vbw",                c_double),
        ("traceLength",        c_int),
        ("window",             c_int),     # SpectrumWindows
        ("verticalUnit",       c_int),     # SpectrumVerticalUnits
        # Read-back fields (populated by GetSettings)
        ("actualStartFreq",    c_double),
        ("actualStopFreq",     c_double),
        ("actualFreqStepSize", c_double),
        ("actualRBW",          c_double),
        ("actualVBW",          c_double),
        ("actualNumIQSamples", c_int),
    ]


# ── Driver ─────────────────────────────────────────────────────────────────────

class RSA306BWindowsDriver(BaseSpectrumDriver):
    """
    Windows ctypes driver for the Tektronix RSA306B.

    Parameters
    ----------
    device_index : int
        USB device index (0-based, default 0).
    rbw_hz : float
        Resolution bandwidth per 40-MHz segment (default 10 kHz).
    trace_length : int
        Spectrum points per segment (default 801, must be odd).
    ref_level_dbm : float
        Reference level in dBm (default 0.0).
    dll_path : str
        Full path to RSA_API.dll.
    """

    def __init__(
        self,
        device_index: int = 0,
        rbw_hz: float = _DEFAULT_RBW_HZ,
        trace_length: int = _DEFAULT_TRACE_LEN,
        ref_level_dbm: float = 0.0,
        dll_path: str = _DEFAULT_DLL_PATH,
    ) -> None:
        self._dev_idx       = device_index
        self._rbw_hz        = rbw_hz
        self._trace_length  = trace_length
        self._ref_level_dbm = ref_level_dbm
        self._dll_path      = dll_path
        self._dll           = None   # CDLL instance, set in connect()

    # ── BaseSpectrumDriver properties ──────────────────────────────────────────

    @property
    def freq_min_hz(self) -> float:
        return _FREQ_MIN_HZ

    @property
    def freq_max_hz(self) -> float:
        return _FREQ_MAX_HZ

    @property
    def max_span_per_segment_hz(self) -> float:
        return _MAX_BW_HZ

    # ── Connection lifecycle ───────────────────────────────────────────────────

    def connect(self) -> None:
        import os
        log.info("Loading RSA_API.dll from %s", self._dll_path)
        try:
            # RSA_API.dll lives deep inside SignalVu-PC and depends on DLLs
            # scattered across several parent directories. Add every ancestor
            # up to (and including) the SignalVu-PC root so Windows can resolve
            # all transitive dependencies without requiring PATH changes.
            dll_dir = os.path.dirname(os.path.abspath(self._dll_path))
            search_dir = dll_dir
            for _ in range(6):  # walk up at most 6 levels
                os.add_dll_directory(search_dir)
                parent = os.path.dirname(search_dir)
                if parent == search_dir:
                    break
                search_dir = parent
            dll = CDLL(self._dll_path)
        except OSError as exc:
            raise RuntimeError(
                f"Failed to load RSA_API.dll from '{self._dll_path}': {exc}\n"
                "Ensure SignalVu-PC or the RSA API for Windows is installed, "
                "and set dll_path in config.yaml to the correct location."
            ) from exc

        # Set return types for functions that return non-int values
        dll.DEVICE_GetErrorString.restype = c_char_p

        log.info("Searching for RSA306B devices via USB …")
        num_devices  = c_int(0)
        device_ids   = (c_int * _DEVSRCH_MAX_NUM_DEVICES)()
        device_sns   = (c_char * (_DEVSRCH_SERIAL_MAX_STRLEN * _DEVSRCH_MAX_NUM_DEVICES))()
        device_types = (c_char * (_DEVSRCH_TYPE_MAX_STRLEN   * _DEVSRCH_MAX_NUM_DEVICES))()

        rs = dll.DEVICE_Search(byref(num_devices), device_ids, device_sns, device_types)
        self._check(dll, rs, "DEVICE_Search")

        n = num_devices.value
        log.info("Found %d RSA306B device(s)", n)
        if n == 0:
            raise RuntimeError("No RSA306B devices found via USB")
        if self._dev_idx >= n:
            raise RuntimeError(
                f"device_index={self._dev_idx} out of range (found {n} device(s))"
            )

        rs = dll.DEVICE_Connect(c_int(device_ids[self._dev_idx]))
        self._check(dll, rs, "DEVICE_Connect")
        log.info("Connected to RSA306B device index %d", self._dev_idx)

        rs = dll.CONFIG_SetReferenceLevel(c_double(self._ref_level_dbm))
        self._check(dll, rs, "CONFIG_SetReferenceLevel")

        self._dll = dll

    def disconnect(self) -> None:
        if self._dll is not None:
            try:
                self._dll.DEVICE_Stop()
                self._dll.DEVICE_Disconnect()
                log.info("Disconnected from RSA306B")
            except Exception:
                pass
            self._dll = None

    # ── Scan operations ────────────────────────────────────────────────────────

    def band_scan(
        self,
        start_hz: float,
        stop_hz: float,
        step_hz: float = _DEFAULT_RBW_HZ,
        station_id: str = "",
        task_id: str = "",
    ) -> SpectrumFrame:
        self._require_connected()

        start_hz = max(start_hz, _FREQ_MIN_HZ)
        stop_hz  = min(stop_hz,  _FREQ_MAX_HZ)

        seg_span = _MAX_BW_HZ
        seg_step = seg_span / (self._trace_length - 1)

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
        self._require_connected()
        span_hz   = min(span_hz, _MAX_BW_HZ)
        levels    = self._acquire_segment(center_hz, span_hz, self._rbw_hz)
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
        self._require_connected()

        start_hz = max(start_hz, _FREQ_MIN_HZ)
        stop_hz  = min(stop_hz,  _FREQ_MAX_HZ)
        span_hz  = min(demod_bw_hz, _MAX_BW_HZ)

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

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _acquire_segment(
        self,
        center_hz: float,
        span_hz: float,
        rbw_hz: float,
    ) -> np.ndarray:
        """One spectrum acquisition centred on center_hz. Returns float32 dBm array."""
        dll = self._dll

        self._check(dll, dll.CONFIG_SetCenterFreq(c_double(center_hz)),      "CONFIG_SetCenterFreq")
        self._check(dll, dll.CONFIG_SetReferenceLevel(c_double(self._ref_level_dbm)), "CONFIG_SetReferenceLevel")

        settings              = _SpectrumSettings()
        settings.span         = float(span_hz)
        settings.rbw          = float(rbw_hz)
        settings.enableVBW    = False
        settings.vbw          = float(rbw_hz)
        settings.traceLength  = self._trace_length
        settings.window       = _WINDOW_KAISER
        settings.verticalUnit = _VERT_UNIT_DBM
        self._check(dll, dll.SPECTRUM_SetSettings(settings), "SPECTRUM_SetSettings")

        self._check(dll, dll.SPECTRUM_SetEnable(c_bool(True)), "SPECTRUM_SetEnable")
        self._check(dll, dll.DEVICE_Run(),                     "DEVICE_Run")
        self._check(dll, dll.SPECTRUM_AcquireTrace(),          "SPECTRUM_AcquireTrace")

        ready = c_bool(False)
        self._check(
            dll,
            dll.SPECTRUM_WaitForTraceReady(c_int(_WAIT_TIMEOUT_MS), byref(ready)),
            "SPECTRUM_WaitForTraceReady",
        )

        if not ready.value:
            log.warning(
                "RSA306B: data not ready after %d ms for centre=%.3f MHz",
                _WAIT_TIMEOUT_MS, center_hz / 1e6,
            )
            dll.DEVICE_Stop()
            return np.full(self._trace_length, np.nan, dtype=np.float32)

        trace_data = (c_float * self._trace_length)()
        out_len    = c_int(0)
        self._check(
            dll,
            dll.SPECTRUM_GetTrace(
                c_int(_TRACE1),
                c_int(self._trace_length),
                trace_data,
                byref(out_len),
            ),
            "SPECTRUM_GetTrace",
        )
        dll.DEVICE_Stop()

        levels = np.frombuffer(trace_data, dtype=np.float32)[:out_len.value].copy()
        log.debug(
            "RSA306B segment: centre=%.3f MHz span=%.1f MHz → %d pts",
            center_hz / 1e6, span_hz / 1e6, len(levels),
        )
        return levels

    @staticmethod
    def _check(dll, rs: int, fn_name: str) -> None:
        if rs != _NO_ERROR:
            try:
                msg = dll.DEVICE_GetErrorString(c_int(rs))
                err_str = msg.decode() if msg else f"error code {rs}"
            except Exception:
                err_str = f"error code {rs}"
            raise RuntimeError(f"RSA306B {fn_name} failed: {err_str}")

    def _require_connected(self) -> None:
        if self._dll is None:
            raise RuntimeError(
                "RSA306B not connected.  Call connect() first, "
                "or use the driver as a context manager."
            )

    def __repr__(self) -> str:
        status = "connected" if self._dll else "disconnected"
        return (
            f"RSA306BWindowsDriver(device_index={self._dev_idx}, "
            f"rbw={self._rbw_hz:.0f} Hz, {status})"
        )

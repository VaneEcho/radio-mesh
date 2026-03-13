"""
Mock Spectrum Driver — no hardware required
============================================
Generates synthetic spectrum data for development and testing.

Simulated environment
---------------------
  Noise floor   : Gaussian noise centred at -105 dBm (σ = 2 dBm)
  Synthetic signals (always present):
    FM broadcast  87.5–108 MHz   every 200 kHz   −62 to −42 dBm
    VHF aviation 118–137 MHz     every 25  kHz   −85 to −75 dBm  (sparse)
    VHF marine   156–174 MHz     every 25  kHz   −88 to −78 dBm  (sparse)
    LTE 700      703–803 MHz     every 5   MHz   −72 to −62 dBm
    GSM 900      880–960 MHz     every 200 kHz   −75 to −65 dBm
    LTE 1800    1805–1880 MHz    every 5   MHz   −70 to −60 dBm
    LTE 2100    2110–2170 MHz    every 5   MHz   −68 to −58 dBm
    LTE 2600    2620–2690 MHz    every 5   MHz   −70 to −60 dBm

Config parameters (under device:)
----------------------------------
  scan_delay_s : float   per-sweep sleep, default 0.0
                          set to e.g. 0.5 to emulate slower hardware
  seed         : int      RNG seed for reproducible output; omit for random

Usage
-----
  device:
    type: mock
    scan_delay_s: 0.0
    seed: 42
"""
from __future__ import annotations

import math
import time

import numpy as np

from .base import BaseSpectrumDriver, SpectrumFrame

# ── Synthetic signal table ────────────────────────────────────────────────────
# Each entry: (start_hz, stop_hz, spacing_hz, level_min_dbm, level_max_dbm)
_SIGNALS: list[tuple[float, float, float, float, float]] = [
    (87.5e6,   108e6,   200e3,  -62.0, -42.0),   # FM broadcast
    (118e6,    137e6,    25e3,  -85.0, -75.0),   # VHF aviation
    (156e6,    174e6,    25e3,  -88.0, -78.0),   # VHF marine
    (703e6,    803e6,     5e6,  -72.0, -62.0),   # LTE 700
    (880e6,    960e6,   200e3,  -75.0, -65.0),   # GSM 900
    (1805e6,  1880e6,     5e6,  -70.0, -60.0),   # LTE 1800
    (2110e6,  2170e6,     5e6,  -68.0, -58.0),   # LTE 2100
    (2620e6,  2690e6,     5e6,  -70.0, -60.0),   # LTE 2600
]

_NOISE_FLOOR_DBM: float = -105.0
_NOISE_SIGMA_DBM: float = 2.0
_SIGNAL_BW_BINS: int = 3        # width of each synthetic signal in frequency bins


class MockDriver(BaseSpectrumDriver):
    """
    Synthetic spectrum driver for development and CI use.

    Parameters
    ----------
    scan_delay_s : float
        Sleep per call to simulate hardware scan time.  0 = instant.
    seed : int or None
        NumPy RNG seed.  None = non-reproducible (default).
    """

    def __init__(
        self,
        scan_delay_s: float = 0.0,
        seed: int | None = None,
    ) -> None:
        self._delay = scan_delay_s
        self._rng = np.random.default_rng(seed)

    # ── BaseSpectrumDriver properties ─────────────────────────────────────

    @property
    def freq_min_hz(self) -> float:
        return 9e3          # 9 kHz (generous lower bound)

    @property
    def freq_max_hz(self) -> float:
        return 8e9          # 8 GHz

    @property
    def max_span_per_segment_hz(self) -> float:
        return 8e9          # no hardware segmentation limit

    # ── Connection lifecycle ───────────────────────────────────────────────

    def connect(self) -> None:
        pass    # nothing to open

    def disconnect(self) -> None:
        pass    # nothing to close

    # ── Scan operations ───────────────────────────────────────────────────

    def band_scan(
        self,
        start_hz: float,
        stop_hz: float,
        step_hz: float,
        station_id: str = "",
        task_id: str = "",
    ) -> SpectrumFrame:
        if self._delay > 0:
            time.sleep(self._delay)

        n = math.ceil((stop_hz - start_hz) / step_hz) + 1
        levels = self._generate_spectrum(start_hz, step_hz, n)

        return SpectrumFrame(
            station_id=station_id,
            timestamp_ms=SpectrumFrame.now_ms(),
            freq_start_hz=float(start_hz),
            freq_step_hz=float(step_hz),
            levels_dbm=levels,
            task_id=task_id,
            driver="mock",
        )

    def if_analysis(
        self,
        center_hz: float,
        span_hz: float,
        station_id: str = "",
        task_id: str = "",
    ) -> SpectrumFrame:
        if self._delay > 0:
            time.sleep(self._delay * 0.1)

        n = 2049
        step = span_hz / (n - 1)
        start_hz = center_hz - span_hz / 2.0
        levels = self._generate_spectrum(start_hz, step, n)

        return SpectrumFrame(
            station_id=station_id,
            timestamp_ms=SpectrumFrame.now_ms(),
            freq_start_hz=float(start_hz),
            freq_step_hz=float(step),
            levels_dbm=levels,
            task_id=task_id,
            driver="mock-ifpan",
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
        if self._delay > 0:
            time.sleep(self._delay * 0.5)

        n = math.ceil((stop_hz - start_hz) / step_hz) + 1
        levels = self._generate_spectrum(start_hz, step_hz, n)

        return SpectrumFrame(
            station_id=station_id,
            timestamp_ms=SpectrumFrame.now_ms(),
            freq_start_hz=float(start_hz),
            freq_step_hz=float(step_hz),
            levels_dbm=levels,
            task_id=task_id,
            driver="mock-fscan",
        )

    # ── Spectrum generation ───────────────────────────────────────────────

    def _generate_spectrum(
        self,
        start_hz: float,
        step_hz: float,
        n: int,
    ) -> np.ndarray:
        """
        Return float32 array of n synthetic power levels (dBm).

        Algorithm:
          1. Fill with Gaussian noise centred at _NOISE_FLOOR_DBM.
          2. For each synthetic signal whose centre falls within the
             requested range, add a Gaussian bump (_SIGNAL_BW_BINS wide)
             at the signal's level.
        """
        levels = self._rng.normal(
            loc=_NOISE_FLOOR_DBM,
            scale=_NOISE_SIGMA_DBM,
            size=n,
        ).astype(np.float32)

        stop_hz = start_hz + step_hz * (n - 1)

        for sig_start, sig_stop, spacing, lvl_min, lvl_max in _SIGNALS:
            # Generate signal centre frequencies within the requested range
            first = max(sig_start, start_hz)
            last  = min(sig_stop,  stop_hz)
            if first >= last:
                continue

            # Align first to nearest spacing multiple above sig_start
            offset = first - sig_start
            first_aligned = sig_start + math.ceil(offset / spacing) * spacing

            freq = first_aligned
            while freq <= last:
                bin_idx = round((freq - start_hz) / step_hz)
                if 0 <= bin_idx < n:
                    # Random level for this signal instance
                    sig_level = float(
                        self._rng.uniform(lvl_min, lvl_max)
                    )
                    # Gaussian bump centred at bin_idx
                    for offset_bin in range(
                        -_SIGNAL_BW_BINS, _SIGNAL_BW_BINS + 1
                    ):
                        b = bin_idx + offset_bin
                        if 0 <= b < n:
                            attenuation = offset_bin ** 2 * 3.0  # dB/bin²
                            levels[b] = max(
                                levels[b],
                                np.float32(sig_level - attenuation),
                            )
                freq += spacing

        return levels

    # ── Repr ──────────────────────────────────────────────────────────────

    def __repr__(self) -> str:
        return f"MockDriver(delay={self._delay}s)"

"""
Abstract base class for all spectrum monitoring device drivers.

Each driver must implement the three standard operations:
  - band_scan()    : PSCan wideband sweep (primary loop operation)
  - if_analysis()  : IF-panorama narrow-band analysis (CW + IFPAN)
  - channel_scan() : Channel-by-channel sweep with demod BW (FSCan mode)

Upper layers only ever see this interface — they are unaware of which
physical device is connected.
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np


@dataclass
class SpectrumFrame:
    """
    A single spectrum sweep result.

    Levels are always in dBm (drivers are responsible for unit conversion).
    freq_start_hz + freq_step_hz * i gives the centre frequency of point i.
    """
    station_id: str
    timestamp_ms: int              # Unix time in milliseconds
    freq_start_hz: float           # Centre freq of first bin
    freq_step_hz: float            # Bin spacing
    levels_dbm: np.ndarray         # float32, shape (N,)
    task_id: str = ""
    driver: str = ""               # e.g. "em550", "rsa306b"

    @property
    def freq_stop_hz(self) -> float:
        return self.freq_start_hz + self.freq_step_hz * (len(self.levels_dbm) - 1)

    @property
    def num_points(self) -> int:
        return len(self.levels_dbm)

    @classmethod
    def now_ms(cls) -> int:
        return int(time.time() * 1000)


class BaseSpectrumDriver(ABC):
    """
    Abstract spectrum driver.  Subclasses implement connect / disconnect and
    the three standard scan operations.
    """

    # ── connection lifecycle ──────────────────────────────────────────────

    @abstractmethod
    def connect(self) -> None:
        """Open the connection to the instrument."""

    @abstractmethod
    def disconnect(self) -> None:
        """Close the connection and release resources."""

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *_):
        self.disconnect()

    # ── Operation 1: Band Scan (PSCan) ───────────────────────────────────

    @abstractmethod
    def band_scan(
        self,
        start_hz: float,
        stop_hz: float,
        step_hz: float,
        station_id: str = "",
        task_id: str = "",
    ) -> SpectrumFrame:
        """
        Wideband panoramic sweep from start_hz to stop_hz.

        Uses PSCan mode.  The driver may internally segment the sweep to
        accommodate hardware limits (e.g. max points per acquisition) and
        returns a single stitched SpectrumFrame.

        Args:
            start_hz:   Sweep start frequency in Hz.
            stop_hz:    Sweep stop frequency in Hz (inclusive).
            step_hz:    Desired frequency step / RBW in Hz.  The driver
                        rounds to the nearest hardware-supported value.
            station_id: Passed through into the returned SpectrumFrame.
            task_id:    Passed through into the returned SpectrumFrame.

        Returns:
            SpectrumFrame with levels in dBm.
        """

    # ── Operation 2: IF Analysis (CW + IFPAN) ────────────────────────────

    @abstractmethod
    def if_analysis(
        self,
        center_hz: float,
        span_hz: float,
        station_id: str = "",
        task_id: str = "",
    ) -> SpectrumFrame:
        """
        Narrow-band IF-panorama analysis centred on center_hz.

        Uses CW + IFPAN mode (requires hardware option EM550SU or EM550IM on
        the EM550).  Suitable for detailed analysis of a specific signal.

        Args:
            center_hz : Centre frequency in Hz.
            span_hz   : IF panorama span in Hz (rounded to nearest valid value).
            station_id: Passed through into the returned SpectrumFrame.
            task_id:    Passed through into the returned SpectrumFrame.

        Returns:
            SpectrumFrame with levels in dBm (fixed number of points per driver).
        """

    # ── Operation 3: Channel Scan (FSCan) ────────────────────────────────

    @abstractmethod
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
        Channel-by-channel frequency scan with a separate demodulation BW.

        Uses FSCan (frequency scan / sweep) mode.  step_hz defines channel
        spacing; demod_bw_hz must be < step_hz to avoid adjacent-channel bleed.
        Suitable for monitoring well-defined channel plans.

        Args:
            start_hz:    First channel centre frequency in Hz.
            stop_hz:     Last channel centre frequency in Hz (inclusive).
            step_hz:     Channel spacing in Hz.
            demod_bw_hz: Demodulation / measurement bandwidth in Hz.
                         Must be ≤ step_hz.
            station_id:  Passed through into the returned SpectrumFrame.
            task_id:     Passed through into the returned SpectrumFrame.

        Returns:
            SpectrumFrame with levels in dBm.
        """

    # ── hardware limits (read-only) ───────────────────────────────────────

    @property
    @abstractmethod
    def freq_min_hz(self) -> float:
        """Minimum tunable frequency in Hz."""

    @property
    @abstractmethod
    def freq_max_hz(self) -> float:
        """Maximum tunable frequency in Hz."""

    @property
    @abstractmethod
    def max_span_per_segment_hz(self) -> float:
        """
        Maximum frequency span that can be captured in a single hardware
        acquisition.  band_scan() uses this to decide how many segments
        are needed.
        """

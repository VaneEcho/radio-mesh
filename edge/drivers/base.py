"""
Abstract base class for all spectrum monitoring device drivers.

Each driver must implement scan_range() and return SpectrumFrame objects.
Upper layers (scan engine, preprocessor) only ever see this interface —
they are unaware of which physical device is connected.
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

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
    Abstract spectrum driver.  Subclasses implement connect / disconnect /
    scan_range and expose hardware limits as properties.
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

    # ── core scan ────────────────────────────────────────────────────────

    @abstractmethod
    def scan_range(
        self,
        start_hz: float,
        stop_hz: float,
        step_hz: float,
        station_id: str = "",
        task_id: str = "",
    ) -> SpectrumFrame:
        """
        Sweep the spectrum from start_hz to stop_hz with the given step.

        The driver may internally segment the sweep to accommodate hardware
        limits (e.g. maximum points per acquisition).  The caller always
        receives a single stitched SpectrumFrame.

        Args:
            start_hz:   Sweep start frequency in Hz.
            stop_hz:    Sweep stop frequency in Hz (inclusive).
            step_hz:    Desired frequency step in Hz.  The driver may
                        round to the nearest hardware-supported value.
            station_id: Passed through into the returned SpectrumFrame.
            task_id:    Passed through into the returned SpectrumFrame.

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
        acquisition.  scan_range() uses this to decide how many segments
        are needed.
        """

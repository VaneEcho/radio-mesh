"""
1-Minute Rolling-Max Aggregator
================================
Accepts SpectrumFrames directly from the driver and maintains a per-freq-bin
rolling maximum level.  Every `interval_s` seconds it fires a callback with
a SpectrumBundle and resets the accumulators.

Design notes:
  - One float32 array (same shape as the incoming frames) holds the
    running max across all sweeps in the current window.
  - No band rules, no channel merging — that is the cloud's job.
  - Thread-safe: scan loop and tick() are called from the same thread.
    No locking needed.  If multi-thread use is required, add a Lock.
"""
from __future__ import annotations

import logging
import time
from typing import Callable

import numpy as np

from .drivers.base import SpectrumFrame
from .models import SpectrumBundle

log = logging.getLogger(__name__)


class Aggregator:
    """
    Rolling-max aggregator with a fixed time window.

    Parameters
    ----------
    station_id : str
        Passed through into every SpectrumBundle.
    interval_s : float
        How often to fire on_bundle (default 60 seconds).
    on_bundle : callable
        Called with (SpectrumBundle,) when the window closes.
        Must not raise; exceptions are caught and logged.
    """

    def __init__(
        self,
        station_id: str,
        interval_s: float = 60.0,
        on_bundle: Callable[[SpectrumBundle], None] | None = None,
    ) -> None:
        self._station_id = station_id
        self._interval_s = interval_s
        self._on_bundle = on_bundle

        # Accumulated max levels; None until the first frame arrives
        self._max_levels: np.ndarray | None = None
        self._freq_start_hz: float = 0.0
        self._freq_step_hz: float = 0.0
        self._sweep_count: int = 0

        self._window_start_ms: int = self._now_ms()

    # ── Public API ───────────────────────────────────────────────────────

    def update(self, frame: SpectrumFrame) -> None:
        """
        Ingest one SpectrumFrame from the driver.
        Call this after every band_scan() / channel_scan() call.
        """
        if self._max_levels is None:
            # First frame in this window — initialise accumulators
            self._freq_start_hz = frame.freq_start_hz
            self._freq_step_hz = frame.freq_step_hz
            self._max_levels = frame.levels_dbm.astype(np.float32).copy()
            self._sweep_count = 1
            return

        # Warn if the frequency grid changed (should not happen in normal ops)
        if (
            frame.freq_start_hz != self._freq_start_hz
            or frame.freq_step_hz != self._freq_step_hz
        ):
            log.warning(
                "Aggregator: freq grid changed (%.0f Hz / %.0f Hz step → "
                "%.0f Hz / %.0f Hz step) — resetting window",
                self._freq_start_hz, self._freq_step_hz,
                frame.freq_start_hz, frame.freq_step_hz,
            )
            self._freq_start_hz = frame.freq_start_hz
            self._freq_step_hz = frame.freq_step_hz
            self._max_levels = frame.levels_dbm.astype(np.float32).copy()
            self._sweep_count = 1
            self._window_start_ms = self._now_ms()
            return

        # Element-wise maximum (NaN-safe: np.fmax ignores NaN)
        incoming = frame.levels_dbm.astype(np.float32)
        if len(incoming) != len(self._max_levels):
            # Point count mismatch — take the shorter length defensively
            n = min(len(incoming), len(self._max_levels))
            log.warning(
                "Aggregator: point count changed (%d → %d) — truncating to %d",
                len(self._max_levels), len(incoming), n,
            )
            self._max_levels = np.fmax(self._max_levels[:n], incoming[:n])
        else:
            np.fmax(self._max_levels, incoming, out=self._max_levels)

        self._sweep_count += 1

    def tick(self) -> bool:
        """
        Check whether the aggregation window has elapsed and fire if so.

        Call this once per sweep iteration (after update()).
        Returns True if a bundle was fired this call.
        """
        now = self._now_ms()
        elapsed = (now - self._window_start_ms) / 1000.0

        if elapsed < self._interval_s:
            return False

        self._fire(now)
        return True

    def flush(self) -> SpectrumBundle | None:
        """
        Force-fire the current window immediately (e.g. on shutdown).
        Returns the bundle, or None if no data has been accumulated.
        """
        if self._max_levels is None:
            log.debug("Aggregator flush: no data in window, nothing to emit")
            return None
        now = self._now_ms()
        return self._fire(now)

    @property
    def pending_sweeps(self) -> int:
        """How many sweeps have been accumulated in the current window."""
        return self._sweep_count

    @property
    def window_age_s(self) -> float:
        """Seconds since the current window started."""
        return (self._now_ms() - self._window_start_ms) / 1000.0

    # ── Internal ─────────────────────────────────────────────────────────

    def _fire(self, now_ms: int) -> SpectrumBundle:
        bundle = SpectrumBundle(
            station_id=self._station_id,
            period_start_ms=self._window_start_ms,
            period_end_ms=now_ms,
            sweep_count=self._sweep_count,
            freq_start_hz=self._freq_start_hz,
            freq_step_hz=self._freq_step_hz,
            levels_dbm=self._max_levels.copy(),
        )

        log.info(
            "Aggregator: window %.1f s, %d sweeps, %d bins → firing bundle",
            bundle.duration_s, self._sweep_count, bundle.num_points,
        )

        # Reset for next window
        self._max_levels = None
        self._sweep_count = 0
        self._window_start_ms = now_ms

        if self._on_bundle:
            try:
                self._on_bundle(bundle)
            except Exception:
                log.exception("on_bundle callback raised an exception")

        return bundle

    @staticmethod
    def _now_ms() -> int:
        return int(time.time() * 1000)

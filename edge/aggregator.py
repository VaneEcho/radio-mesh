"""
1-Minute Rolling-Max Aggregator
================================
Accepts ChannelSamples from the preprocessor and maintains a rolling maximum
level per (band_id, channel_idx).  Every `interval_s` seconds it fires a
callback with an AggregatedBundle and resets the accumulators.

Design notes:
  - A full sweep of 20 MHz–3.6 GHz at 25 kHz step takes ~2–3 minutes.
    The aggregator therefore holds "carry-over" from the previous sweep for
    channels not yet refreshed in the current sweep.  Each 1-minute bundle
    contains the most recent valid reading for every channel — the timestamp
    of each ChannelSample tells you exactly when that channel was measured.
  - Thread-safe: the scan loop and the timer fire from the same thread
    (scanner calls update() + tick() in sequence), so no locking is needed.
    If multi-thread use is ever required, add a threading.Lock around _store.
"""
from __future__ import annotations

import logging
import time
from collections import defaultdict
from typing import Callable

from .models import AggregatedBundle, ChannelEntry, ChannelSample

log = logging.getLogger(__name__)


class Aggregator:
    """
    Rolling-max aggregator with a fixed time window.

    Parameters
    ----------
    station_id : str
        Passed through into every AggregatedBundle.
    interval_s : float
        How often to fire on_bundle (default 60 seconds).
    on_bundle : callable
        Called with (AggregatedBundle,) when the window closes.
        Must not raise; exceptions are caught and logged.
    """

    def __init__(
        self,
        station_id: str,
        interval_s: float = 60.0,
        on_bundle: Callable[[AggregatedBundle], None] | None = None,
    ) -> None:
        self._station_id = station_id
        self._interval_s = interval_s
        self._on_bundle = on_bundle

        # (band_id, channel_idx) → (max_level_dbm, sample_count, freq_center_hz)
        self._store: dict[tuple[int, int], tuple[float, int, float]] = {}

        self._window_start_ms: int = self._now_ms()

    # ── Public API ───────────────────────────────────────────────────────

    def update(self, samples: list[ChannelSample]) -> None:
        """
        Ingest a batch of ChannelSamples from one sweep pass.
        Call this after every preprocessor.process() call.
        """
        for s in samples:
            key = (s.band_id, s.channel_idx)
            existing = self._store.get(key)
            if existing is None:
                self._store[key] = (s.level_dbm, 1, s.freq_center_hz)
            else:
                prev_max, count, freq = existing
                new_max = max(prev_max, s.level_dbm)
                self._store[key] = (new_max, count + 1, freq)

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

    def flush(self) -> AggregatedBundle | None:
        """
        Force-fire the current window immediately (e.g. on shutdown).
        Returns the bundle, or None if the store is empty.
        """
        if not self._store:
            log.debug("Aggregator flush: store is empty, nothing to emit")
            return None
        now = self._now_ms()
        return self._fire(now)

    @property
    def pending_channels(self) -> int:
        """How many channels have data in the current window."""
        return len(self._store)

    @property
    def window_age_s(self) -> float:
        """Seconds since the current window started."""
        return (self._now_ms() - self._window_start_ms) / 1000.0

    # ── Internal ─────────────────────────────────────────────────────────

    def _fire(self, now_ms: int) -> AggregatedBundle:
        entries = [
            ChannelEntry(
                band_id=band_id,
                channel_idx=ch_idx,
                freq_center_hz=freq,
                max_level_dbm=max_level,
                sample_count=count,
            )
            for (band_id, ch_idx), (max_level, count, freq)
            in self._store.items()
        ]
        entries.sort(key=lambda e: e.freq_center_hz)

        bundle = AggregatedBundle(
            station_id=self._station_id,
            period_start_ms=self._window_start_ms,
            period_end_ms=now_ms,
            channels=entries,
        )

        log.info(
            "Aggregator: window %.1f s → %d channels → firing bundle",
            bundle.duration_s, len(entries),
        )

        # Reset for next window
        self._store.clear()
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

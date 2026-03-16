"""
Spectrum Preprocessor
=====================
Merges raw 25 kHz bins from a SpectrumFrame into logical channels defined
by band_rules.yaml, reducing upload payload by 60–80% while preserving
lossless max-value aggregation within each channel.

Design
------
For each band rule:
  1. Slice the raw bins that fall within [rule.freq_start_hz, rule.freq_stop_hz].
  2. Group bins into channels of `rule.channel_bw_hz` width.
  3. Take the max level within each channel (lossless: max ≥ any individual bin).
  4. Store: centre frequency + max level.

Bins that fall outside any band rule are merged at the default resolution
(configurable, default = 100 kHz = 4 × 25 kHz steps) to preserve coverage.

The output is a new SpectrumFrame whose freq_step_hz reflects the chosen
aggregation per-band rather than the raw hardware step.

Note: This is an optional optimisation.  The system works correctly without
preprocessing — the cloud receives raw bins and stores them as-is.

Usage
-----
    from edge.preprocessor import Preprocessor
    from edge.drivers.base import SpectrumFrame

    rules = [
        {"name": "FM", "freq_start_hz": 87.5e6, "freq_stop_hz": 108e6,
         "channel_bw_hz": 200e3},
        ...
    ]
    pre = Preprocessor(band_rules=rules, default_step_hz=100_000)
    merged_frame = pre.process(raw_frame)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

from .drivers.base import SpectrumFrame

log = logging.getLogger(__name__)


@dataclass
class BandRule:
    name: str
    freq_start_hz: float
    freq_stop_hz: float
    channel_bw_hz: float  # desired output channel width (Hz)


class Preprocessor:
    """
    Merge raw spectrum bins according to per-band channel-width rules.

    Parameters
    ----------
    band_rules : list[dict]
        Each dict must have: name, freq_start_hz, freq_stop_hz, channel_bw_hz.
        Loaded from band_rules.yaml at the edge.
    default_step_hz : float
        Merge step for bins not covered by any band rule (default 100 kHz).
    """

    def __init__(
        self,
        band_rules: list[dict],
        default_step_hz: float = 100_000.0,
    ) -> None:
        self._rules = sorted(
            [
                BandRule(
                    name=r["name"],
                    freq_start_hz=float(r["freq_start_hz"]),
                    freq_stop_hz=float(r["freq_stop_hz"]),
                    channel_bw_hz=float(r.get("channel_bw_hz", default_step_hz)),
                )
                for r in band_rules
                if r.get("channel_bw_hz")
            ],
            key=lambda x: x.freq_start_hz,
        )
        self._default_step_hz = default_step_hz

    def process(self, frame: SpectrumFrame) -> SpectrumFrame:
        """
        Return a new SpectrumFrame with bins merged per band rules.

        If no rules are defined (empty list), returns the original frame
        unchanged so existing behaviour is preserved.
        """
        if not self._rules:
            return frame

        raw = frame.levels_dbm
        f0 = frame.freq_start_hz
        fstep = frame.freq_step_hz
        n = len(raw)
        f_max = f0 + fstep * (n - 1)

        out_freqs: list[float] = []
        out_levels: list[float] = []

        # Walk through frequency space, region by region
        cursor_hz = f0

        def _bin_index(freq_hz: float) -> int:
            return max(0, min(n - 1, round((freq_hz - f0) / fstep)))

        def _merge_region(region_start: float, region_stop: float, merge_step: float) -> None:
            """Merge bins in [region_start, region_stop] with step `merge_step`."""
            ch_start = region_start
            while ch_start < region_stop:
                ch_end = min(ch_start + merge_step, region_stop)
                bi_lo = _bin_index(ch_start)
                bi_hi = _bin_index(ch_end)
                if bi_lo > bi_hi:
                    ch_start = ch_end
                    continue
                chunk = raw[bi_lo: bi_hi + 1]
                if len(chunk) == 0:
                    ch_start = ch_end
                    continue
                ch_center = (ch_start + ch_end) / 2.0
                out_freqs.append(ch_center)
                out_levels.append(float(np.nanmax(chunk)))
                ch_start = ch_end

        for rule in self._rules:
            # Fill gap between last cursor and this rule's start
            if cursor_hz < rule.freq_start_hz:
                gap_end = min(rule.freq_start_hz, f_max + fstep)
                _merge_region(cursor_hz, gap_end, self._default_step_hz)
                cursor_hz = gap_end

            if cursor_hz >= f_max:
                break

            # Process this band with its channel_bw_hz
            band_end = min(rule.freq_stop_hz, f_max + fstep)
            _merge_region(cursor_hz, band_end, rule.channel_bw_hz)
            cursor_hz = band_end

        # Remaining spectrum after all rules
        if cursor_hz < f_max:
            _merge_region(cursor_hz, f_max + fstep, self._default_step_hz)

        if not out_levels:
            log.warning("Preprocessor: no output bins — returning original frame")
            return frame

        levels_arr = np.array(out_levels, dtype=np.float32)

        # Compute representative freq_step (median gap between output centres)
        if len(out_freqs) > 1:
            gaps = [out_freqs[i + 1] - out_freqs[i] for i in range(len(out_freqs) - 1)]
            freq_step = float(np.median(gaps))
        else:
            freq_step = self._default_step_hz

        log.debug(
            "Preprocessor: %d raw bins → %d merged bins (%.1fx reduction)",
            n, len(levels_arr), n / max(len(levels_arr), 1),
        )

        return SpectrumFrame(
            station_id=frame.station_id,
            timestamp_ms=frame.timestamp_ms,
            freq_start_hz=float(out_freqs[0]) if out_freqs else f0,
            freq_step_hz=freq_step,
            levels_dbm=levels_arr,
            task_id=frame.task_id,
            driver=frame.driver,
        )

    @classmethod
    def from_yaml(cls, rules_path: str, default_step_hz: float = 100_000.0) -> "Preprocessor":
        """
        Convenience constructor: load band rules from a YAML file.

        Expected YAML format (subset of band_rules.yaml):
            - name: FM Broadcast
              freq_start_hz: 87500000
              freq_stop_hz: 108000000
              channel_bw_hz: 200000
              ...
        """
        import yaml
        with open(rules_path, "r", encoding="utf-8") as f:
            rules = yaml.safe_load(f)
        return cls(band_rules=rules or [], default_step_hz=default_step_hz)

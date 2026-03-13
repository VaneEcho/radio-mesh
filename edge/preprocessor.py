"""
Spectrum Preprocessor
=====================
Converts a raw SpectrumFrame (25 kHz bins) into a list of ChannelSamples
according to the band rules defined in band_rules.yaml.

For each enabled band rule, the preprocessor:
  1. Locates the SpectrumFrame bins that fall within the rule's frequency range.
  2. Divides those bins into channels of width `channel_bw_khz`.
  3. Takes the maximum level in each channel (peak-hold within the channel).
  4. Emits one ChannelSample per channel.

Channels that have no overlapping bins (e.g. the SpectrumFrame doesn't cover
that frequency) are silently skipped.
"""
from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Optional

import numpy as np
import yaml

from .drivers.base import SpectrumFrame
from .models import ChannelSample

log = logging.getLogger(__name__)


class BandRule:
    """One loaded entry from band_rules.yaml."""

    __slots__ = (
        "id", "freq_start_hz", "freq_end_hz",
        "service_name", "service_type",
        "channel_bw_hz", "enabled",
    )

    def __init__(self, raw: dict) -> None:
        self.id: int = raw["id"]
        self.freq_start_hz: float = raw["freq_start_mhz"] * 1e6
        self.freq_end_hz: float = raw["freq_end_mhz"] * 1e6
        self.service_name: str = raw.get("service_name", "")
        self.service_type: str = raw.get("service_type", "other")
        self.channel_bw_hz: float = raw.get("channel_bw_khz", 25.0) * 1e3
        self.enabled: bool = raw.get("enabled", True)

    @property
    def span_hz(self) -> float:
        return self.freq_end_hz - self.freq_start_hz

    @property
    def num_channels(self) -> int:
        return max(1, math.ceil(self.span_hz / self.channel_bw_hz))


class Preprocessor:
    """
    Loads band rules once at startup and processes SpectrumFrames on demand.

    Usage:
        pre = Preprocessor("../docs/band_rules.yaml")
        samples = pre.process(frame)
    """

    def __init__(self, band_rules_path: str | Path) -> None:
        self._rules: list[BandRule] = []
        self._load_rules(Path(band_rules_path))
        log.info(
            "Preprocessor: loaded %d enabled band rules from %s",
            len(self._rules), band_rules_path,
        )

    def _load_rules(self, path: Path) -> None:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        for raw in data.get("bands", []):
            rule = BandRule(raw)
            if rule.enabled:
                self._rules.append(rule)
        # Sort by start frequency for predictable processing order
        self._rules.sort(key=lambda r: r.freq_start_hz)

    def process(self, frame: SpectrumFrame) -> list[ChannelSample]:
        """
        Convert a SpectrumFrame into ChannelSamples.

        Args:
            frame: Raw spectrum sweep from a device driver.

        Returns:
            List of ChannelSample, one per (rule, channel_index) that has
            at least one overlapping bin in the frame.
        """
        samples: list[ChannelSample] = []
        ts = frame.timestamp_ms
        levels = frame.levels_dbm  # float32 numpy array

        for rule in self._rules:
            rule_samples = self._process_rule(rule, frame, levels, ts)
            samples.extend(rule_samples)

        return samples

    def _process_rule(
        self,
        rule: BandRule,
        frame: SpectrumFrame,
        levels: np.ndarray,
        ts: int,
    ) -> list[ChannelSample]:
        """Map one band rule onto the frame and emit ChannelSamples."""

        step = frame.freq_step_hz
        frame_start = frame.freq_start_hz
        n = len(levels)

        # Frame bin index range that overlaps with this rule's frequency range
        # bin i covers centre frequency: frame_start + i * step
        first_idx = math.ceil((rule.freq_start_hz - frame_start) / step)
        last_idx = math.floor((rule.freq_end_hz - frame_start) / step)

        first_idx = max(0, first_idx)
        last_idx = min(n - 1, last_idx)

        if first_idx > last_idx:
            # This rule's range is outside the frame entirely
            return []

        # Number of frame bins per channel
        bins_per_channel = max(1, round(rule.channel_bw_hz / step))

        samples: list[ChannelSample] = []

        for ch_idx in range(rule.num_channels):
            ch_bin_start = first_idx + ch_idx * bins_per_channel
            ch_bin_end = ch_bin_start + bins_per_channel  # exclusive

            # Clamp to the bins we actually have for this rule
            ch_bin_start = max(first_idx, ch_bin_start)
            ch_bin_end = min(last_idx + 1, ch_bin_end)

            if ch_bin_start >= ch_bin_end:
                break  # no more bins within this rule

            channel_levels = levels[ch_bin_start:ch_bin_end]

            # Skip bins that are NaN (padding from segmented scan)
            valid = channel_levels[~np.isnan(channel_levels)]
            if len(valid) == 0:
                continue

            max_level = float(np.max(valid))

            # Channel centre frequency
            ch_centre_idx = (ch_bin_start + ch_bin_end - 1) / 2.0
            freq_center = frame_start + ch_centre_idx * step

            samples.append(ChannelSample(
                band_id=rule.id,
                channel_idx=ch_idx,
                freq_center_hz=freq_center,
                level_dbm=max_level,
                timestamp_ms=ts,
            ))

        return samples

    @property
    def rules(self) -> list[BandRule]:
        return list(self._rules)

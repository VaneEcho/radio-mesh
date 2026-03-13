"""
Shared data models for the RF·MESH edge agent.

Data flow:
  SpectrumFrame  (from driver)
       ↓ preprocessor
  list[ChannelSample]
       ↓ aggregator
  AggregatedBundle
       ↓ uploader
  HTTP POST  /  local log file
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ChannelSample:
    """
    Level reading for a single channel within a frequency band.

    One ChannelSample is produced per (band_rule, channel_index) per sweep.
    The channel's centre frequency is:
        freq_start_hz + channel_idx * channel_bw_hz + channel_bw_hz / 2
    """
    band_id: int           # band_rules.yaml id
    channel_idx: int       # 0-based index within the band
    freq_center_hz: float  # centre frequency of this channel (Hz)
    level_dbm: float       # measured peak/avg level (dBm)
    timestamp_ms: int      # when the sweep covering this channel was captured

    @staticmethod
    def now_ms() -> int:
        return int(time.time() * 1000)


@dataclass
class ChannelEntry:
    """
    One entry in an AggregatedBundle.
    Represents the maximum level seen in a channel over the aggregation window.
    """
    band_id: int
    channel_idx: int
    freq_center_hz: float
    max_level_dbm: float
    sample_count: int      # how many sweep samples contributed


@dataclass
class AggregatedBundle:
    """
    A 1-minute aggregated statistics package ready for upload to Cloud.

    Contains the rolling-maximum level for every channel that received at
    least one sample during the aggregation window.
    """
    station_id: str
    period_start_ms: int
    period_end_ms: int
    channels: list[ChannelEntry] = field(default_factory=list)

    @property
    def duration_s(self) -> float:
        return (self.period_end_ms - self.period_start_ms) / 1000.0

    def to_dict(self) -> dict:
        """Serialize to a plain dict for JSON upload."""
        return {
            "station_id": self.station_id,
            "period_start_ms": self.period_start_ms,
            "period_end_ms": self.period_end_ms,
            "duration_s": round(self.duration_s, 1),
            "channels": [
                {
                    "band_id": ch.band_id,
                    "channel_idx": ch.channel_idx,
                    "freq_center_hz": ch.freq_center_hz,
                    "max_level_dbm": round(ch.max_level_dbm, 1),
                    "sample_count": ch.sample_count,
                }
                for ch in self.channels
            ],
        }

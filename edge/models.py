"""
Shared data models for the RF·MESH edge agent.

Data flow:
  SpectrumFrame  (from driver)
       ↓ aggregator (per freq-bin rolling max, time compression)
  SpectrumBundle
       ↓ uploader
  HTTP POST  /  local JSON file
"""
from __future__ import annotations

import base64
import gzip
import struct
from dataclasses import dataclass

import numpy as np


@dataclass
class SpectrumBundle:
    """
    One aggregation window of spectrum data ready for upload to Cloud.

    Contains the rolling-maximum level for every 25 kHz frequency bin
    across the aggregation window (default 60 s).  The level array is
    transmitted as base64(gzip(float32[])) to minimise bandwidth.

    Upload JSON shape
    -----------------
    {
        "station_id":      "site-01",
        "period_start_ms": 1700000000000,
        "period_end_ms":   1700000060000,
        "sweep_count":     30,
        "freq_start_hz":   20000000.0,
        "freq_step_hz":    25000.0,
        "num_points":      143200,
        "levels_dbm_b64":  "<base64(gzip(float32[num_points]))>"
    }
    """
    station_id: str
    period_start_ms: int
    period_end_ms: int
    sweep_count: int
    freq_start_hz: float
    freq_step_hz: float
    levels_dbm: np.ndarray   # float32, shape (num_points,)

    @property
    def num_points(self) -> int:
        return len(self.levels_dbm)

    @property
    def duration_s(self) -> float:
        return (self.period_end_ms - self.period_start_ms) / 1000.0

    @property
    def freq_stop_hz(self) -> float:
        return self.freq_start_hz + self.freq_step_hz * (self.num_points - 1)

    def to_dict(self) -> dict:
        """Serialize to a plain dict for JSON upload."""
        raw = self.levels_dbm.astype(np.float32).tobytes()
        compressed = gzip.compress(raw, compresslevel=6)
        b64 = base64.b64encode(compressed).decode("ascii")
        return {
            "station_id": self.station_id,
            "period_start_ms": self.period_start_ms,
            "period_end_ms": self.period_end_ms,
            "sweep_count": self.sweep_count,
            "freq_start_hz": self.freq_start_hz,
            "freq_step_hz": self.freq_step_hz,
            "num_points": self.num_points,
            "levels_dbm_b64": b64,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SpectrumBundle":
        """Deserialize from a plain dict (for testing / local read-back)."""
        compressed = base64.b64decode(d["levels_dbm_b64"])
        raw = gzip.decompress(compressed)
        levels = np.frombuffer(raw, dtype=np.float32).copy()
        return cls(
            station_id=d["station_id"],
            period_start_ms=d["period_start_ms"],
            period_end_ms=d["period_end_ms"],
            sweep_count=d["sweep_count"],
            freq_start_hz=d["freq_start_hz"],
            freq_step_hz=d["freq_step_hz"],
            levels_dbm=levels,
        )

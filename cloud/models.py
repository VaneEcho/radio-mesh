"""
RF·MESH Cloud Backend — Pydantic models.

Request / response schemas for the REST API.
"""
from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field


# ── Ingest (edge → cloud) ─────────────────────────────────────────────────────

class SpectrumBundleIn(BaseModel):
    """
    Bundle uploaded by an edge agent.

    levels_dbm_b64: base64( gzip( float32[num_points] ) )
    The float32 array contains rolling-max dBm values; one entry per freq bin.
    """
    station_id: str
    period_start_ms: int
    period_end_ms: int
    sweep_count: int
    freq_start_hz: float
    freq_step_hz: float
    num_points: int
    levels_dbm_b64: str        # base64(gzip(float32[]))


class BundleAck(BaseModel):
    ok: bool = True
    frame_id: int              # auto-assigned DB primary key


# ── Spectrum query ────────────────────────────────────────────────────────────

class SpectrumQueryParams(BaseModel):
    station_id: str
    start_ms: int
    end_ms: int
    freq_start_hz: Optional[float] = None  # optional freq slice
    freq_stop_hz: Optional[float] = None


class SpectrumRow(BaseModel):
    frame_id: int
    station_id: str
    period_start_ms: int
    period_end_ms: int
    sweep_count: int
    freq_start_hz: float
    freq_step_hz: float
    num_points: int
    levels_dbm_b64: str


class SpectrumQueryResponse(BaseModel):
    rows: list[SpectrumRow]
    total: int


# ── Band rules ────────────────────────────────────────────────────────────────

class BandRuleIn(BaseModel):
    name: str
    freq_start_hz: float
    freq_stop_hz: float
    service: str                        # e.g. "FM Broadcast"
    authority: Optional[str] = None     # e.g. "MIIT Order #62 (2023)"
    notes: Optional[str] = None


class BandRuleOut(BandRuleIn):
    rule_id: int

    model_config = {"from_attributes": True}


class BandRuleListResponse(BaseModel):
    rules: list[BandRuleOut]
    total: int


# ── Stations ──────────────────────────────────────────────────────────────────

class StationRegisterIn(BaseModel):
    """Sent by an edge node on startup to announce itself."""
    station_id: str
    name: str


class StationRegisterAck(BaseModel):
    ok: bool = True
    station_id: str


class StationOut(BaseModel):
    station_id: str
    name: str
    last_seen_ms: Optional[int] = None
    online: bool

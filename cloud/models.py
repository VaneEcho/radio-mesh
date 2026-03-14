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


# ── Tasks ─────────────────────────────────────────────────────────────────────

class TaskCreate(BaseModel):
    type: str                           # band_scan / channel_scan / if_analysis
    params: dict                        # scan parameters (see REQUIREMENTS §7.2)
    station_ids: list[str]
    stream_fps: int = Field(default=0, ge=0, le=30)


class TaskStationOut(BaseModel):
    station_id: str
    status: str
    dispatched_at: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    result_b64: Optional[str] = None
    result_meta: Optional[str] = None
    error: Optional[str] = None


class TaskOut(BaseModel):
    task_id: str
    type: str
    params: str
    stream_fps: int
    status: str
    created_at: str
    updated_at: str
    stations: list[TaskStationOut] = []


class TaskSummary(BaseModel):
    task_id: str
    type: str
    status: str
    created_at: str
    station_count: int
    completed_count: int


class TaskListResponse(BaseModel):
    tasks: list[TaskSummary]
    total: int


class TaskResultIn(BaseModel):
    """Posted by edge agent to report task result."""
    station_id: str
    result_b64: Optional[str] = None
    result_meta: Optional[dict] = None
    error: Optional[str] = None


# ── Freq-timeseries ───────────────────────────────────────────────────────────

class FreqTimePoint(BaseModel):
    t: int
    dbm: float


class FreqStationSeries(BaseModel):
    station_id: str
    name: Optional[str] = None
    max_dbm: float
    median_dbm: float
    frame_count: int
    series: list[FreqTimePoint]


class FreqTimeseriesResponse(BaseModel):
    freq_hz: float
    start_ms: int
    end_ms: int
    stations: list[FreqStationSeries]


# ── Freq-assign ───────────────────────────────────────────────────────────────

class FreqAssignRequest(BaseModel):
    station_id: str
    start_hz: float
    stop_hz: float
    channel_bw_hz: float
    threshold_dbm: float = Field(default=-90.0, description="Channels below this are considered free")
    lookback_s: int = Field(default=3600, ge=60, le=604800,
                            description="Observation window in seconds (default 1 h)")


class ChannelEntry(BaseModel):
    channel_idx: int
    center_hz: float
    start_hz: float
    stop_hz: float
    max_dbm: Optional[float] = None    # None = no data for this channel
    free: bool                          # True if max_dbm < threshold or no data


class FreqAssignResponse(BaseModel):
    station_id: str
    start_hz: float
    stop_hz: float
    channel_bw_hz: float
    threshold_dbm: float
    lookback_s: int
    total_channels: int
    free_channels: int
    channels: list[ChannelEntry]

"""
Spectrum query router.

GET /api/v1/spectrum/query              — time-range query, returns compressed frames
GET /api/v1/spectrum/freq-timeseries    — single-freq query across all stations
"""
from __future__ import annotations

import asyncio
import logging
import statistics
from functools import partial

from fastapi import APIRouter, HTTPException, Query, status

from .. import db
from ..models import (
    FreqStationSeries, FreqTimePoint, FreqTimeseriesResponse,
    SpectrumQueryResponse, SpectrumRow,
)

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/spectrum", tags=["query"])


@router.get("/query", response_model=SpectrumQueryResponse)
async def query_spectrum(
    station_id: str = Query(..., description="Station ID"),
    start_ms: int = Query(..., description="Window start (Unix ms)"),
    end_ms: int = Query(..., description="Window end (Unix ms)"),
    limit: int = Query(500, ge=1, le=2000, description="Max rows to return"),
) -> SpectrumQueryResponse:
    """
    Return all stored spectrum frames for a station within the given time window.

    Each row contains a `levels_dbm_b64` field:
    `base64( gzip( float32[num_points] ) )`.
    Decode on the client to get the full dBm array.
    """
    if end_ms <= start_ms:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="end_ms must be greater than start_ms",
        )

    loop = asyncio.get_running_loop()
    rows = await loop.run_in_executor(
        None,
        partial(
            db.query_bundles,
            station_id=station_id,
            start_ms=start_ms,
            end_ms=end_ms,
            limit=limit,
        ),
    )

    return SpectrumQueryResponse(
        rows=[SpectrumRow(**r) for r in rows],
        total=len(rows),
    )


@router.get("/freq-timeseries", response_model=FreqTimeseriesResponse)
async def query_freq_timeseries(
    freq_hz: float = Query(..., description="Frequency to query (Hz)"),
    start_ms: int  = Query(..., description="Window start (Unix ms)"),
    end_ms: int    = Query(..., description="Window end (Unix ms)"),
    station_ids: str = Query("", description="Comma-separated station IDs; empty = all"),
) -> FreqTimeseriesResponse:
    """
    Extract the power level at a single frequency from every stored frame,
    across all stations (or the specified subset), within the time window.

    Returns one time series per station, sorted by time.  Each series also
    carries pre-computed max / median so the caller can rank stations without
    iterating the series data.
    """
    if end_ms <= start_ms:
        raise HTTPException(422, "end_ms must be greater than start_ms")

    sids = [s.strip() for s in station_ids.split(",") if s.strip()] or None

    loop = asyncio.get_running_loop()
    raw = await loop.run_in_executor(
        None,
        partial(db.query_freq_timeseries, freq_hz, start_ms, end_ms, sids),
    )

    # Fetch station names for display
    all_stations = await loop.run_in_executor(None, db.list_stations)
    name_map = {s["station_id"]: s["name"] for s in all_stations}

    station_series = []
    for item in raw:
        dbm_vals = [p["dbm"] for p in item["series"]]
        if not dbm_vals:
            continue
        station_series.append(FreqStationSeries(
            station_id=item["station_id"],
            name=name_map.get(item["station_id"]),
            max_dbm=max(dbm_vals),
            median_dbm=round(statistics.median(dbm_vals), 2),
            frame_count=len(dbm_vals),
            series=[FreqTimePoint(**p) for p in item["series"]],
        ))

    # Sort by max_dbm descending (stations with strongest signal first)
    station_series.sort(key=lambda s: s.max_dbm, reverse=True)

    return FreqTimeseriesResponse(
        freq_hz=freq_hz,
        start_ms=start_ms,
        end_ms=end_ms,
        stations=station_series,
    )

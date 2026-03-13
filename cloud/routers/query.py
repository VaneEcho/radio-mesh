"""
Spectrum query router.

GET /api/v1/spectrum/query   — time-range query, returns raw compressed frames
"""
from __future__ import annotations

import asyncio
import logging
from functools import partial

from fastapi import APIRouter, HTTPException, Query, status

from .. import db
from ..models import SpectrumQueryResponse, SpectrumRow

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

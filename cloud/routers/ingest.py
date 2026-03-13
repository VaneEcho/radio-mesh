"""
Ingest router — receives spectrum bundles from edge agents.

POST /api/v1/spectrum/bundle
"""
from __future__ import annotations

import asyncio
import logging
from functools import partial

from fastapi import APIRouter, HTTPException, status

from .. import db
from ..models import BundleAck, SpectrumBundleIn

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/spectrum", tags=["ingest"])


@router.post("/bundle", response_model=BundleAck, status_code=status.HTTP_201_CREATED)
async def receive_bundle(bundle: SpectrumBundleIn) -> BundleAck:
    """
    Accept a 1-minute aggregated spectrum bundle from an edge station.

    The `levels_dbm_b64` field must be base64( gzip( float32[num_points] ) ).
    """
    loop = asyncio.get_running_loop()
    try:
        frame_id = await loop.run_in_executor(
            None,
            partial(
                db.insert_bundle,
                station_id=bundle.station_id,
                period_start_ms=bundle.period_start_ms,
                period_end_ms=bundle.period_end_ms,
                sweep_count=bundle.sweep_count,
                freq_start_hz=bundle.freq_start_hz,
                freq_step_hz=bundle.freq_step_hz,
                num_points=bundle.num_points,
                levels_dbm_b64=bundle.levels_dbm_b64,
            ),
        )
    except Exception as exc:
        log.exception("Failed to store bundle from station %s", bundle.station_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Storage error: {exc}",
        ) from exc

    return BundleAck(ok=True, frame_id=frame_id)

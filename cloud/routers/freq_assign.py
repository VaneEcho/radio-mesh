"""
Frequency Assignment router
============================
Given a frequency band, channel width, and power threshold, compute which
channels appear to be free based on recent spectrum measurements.

Endpoint
--------
POST /api/v1/freq-assign

Algorithm
---------
1. Fetch all stored spectrum frames for the station within the lookback window
   that cover [start_hz, stop_hz].
2. For each channel (width = channel_bw_hz), compute the rolling max dBm
   across all fetched frames.
3. A channel is "free" if max_dbm < threshold_dbm (or has no measurement data).
4. Return full channel table sorted by center frequency.
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException

from .. import db
from ..models import ChannelEntry, FreqAssignRequest, FreqAssignResponse

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/freq-assign", tags=["freq-assign"])


@router.post("", response_model=FreqAssignResponse)
async def compute_free_channels(body: FreqAssignRequest) -> FreqAssignResponse:
    """
    Scan stored spectrum data for a station and return a channel-by-channel
    occupancy table with free/busy classification.
    """
    if body.stop_hz <= body.start_hz:
        raise HTTPException(422, "stop_hz must be greater than start_hz")
    if body.channel_bw_hz <= 0:
        raise HTTPException(422, "channel_bw_hz must be positive")

    span = body.stop_hz - body.start_hz
    if span / body.channel_bw_hz > 10_000:
        raise HTTPException(
            422,
            f"Too many channels ({span / body.channel_bw_hz:.0f}).  "
            f"Reduce the band span or increase channel_bw_hz.",
        )

    lookback_ms = body.lookback_s * 1000
    loop = asyncio.get_running_loop()
    rows = await loop.run_in_executor(
        None,
        db.query_channel_max_levels,
        body.station_id,
        body.start_hz,
        body.stop_hz,
        body.channel_bw_hz,
        lookback_ms,
    )

    channels = []
    for r in rows:
        max_dbm = r["max_dbm"]
        free = (max_dbm is None) or (max_dbm < body.threshold_dbm)
        channels.append(ChannelEntry(
            channel_idx=r["channel_idx"],
            center_hz=r["center_hz"],
            start_hz=r["start_hz"],
            stop_hz=r["stop_hz"],
            max_dbm=max_dbm,
            free=free,
        ))

    free_count = sum(1 for c in channels if c.free)
    log.info(
        "freq-assign: station=%s band=%.0f-%.0f MHz bw=%.0f kHz "
        "threshold=%.0f dBm → %d/%d free",
        body.station_id,
        body.start_hz / 1e6, body.stop_hz / 1e6,
        body.channel_bw_hz / 1e3,
        body.threshold_dbm,
        free_count, len(channels),
    )

    return FreqAssignResponse(
        station_id=body.station_id,
        start_hz=body.start_hz,
        stop_hz=body.stop_hz,
        channel_bw_hz=body.channel_bw_hz,
        threshold_dbm=body.threshold_dbm,
        lookback_s=body.lookback_s,
        total_channels=len(channels),
        free_channels=free_count,
        channels=channels,
    )

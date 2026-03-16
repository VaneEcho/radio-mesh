"""
Real-time Spectrum Stream
=========================
Frontend clients subscribe here to receive live spectrum frames
forwarded from edge stations.

WebSocket endpoint
------------------
WS /api/v1/stream/{station_id}/ws

    Protocol (server → client only):

    {"type": "stream_frame",
     "station_id": "<id>",
     "b64":        "<base64(gzip(float32[]))>",
     "meta":       {"freq_start_hz": float,
                    "freq_step_hz":  float,
                    "num_points":    int}}

    {"type": "subscribed",
     "station_id": "<id>",
     "message":    "Subscribed to live stream"}

REST endpoint
-------------
GET /api/v1/stream/subscribers
    Returns current subscriber counts per station (for diagnostics).
"""
from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..stream_manager import stream_manager

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/stream", tags=["stream"])


@router.websocket("/{station_id}/ws")
async def frontend_stream_ws(websocket: WebSocket, station_id: str) -> None:
    """
    Frontend subscribes here to receive live spectrum frames for one station.

    The connection is read-only from the frontend's perspective — the server
    only sends frames.  The frontend may send a JSON ping to keep-alive if
    needed, but the server ignores it.
    """
    await websocket.accept()
    client_id = str(uuid.uuid4())[:8]
    log.info("Stream WS connect: station=%s client=%s", station_id, client_id)

    await stream_manager.subscribe(station_id, websocket, client_id)

    # Notify client that subscription is active
    try:
        await websocket.send_json({
            "type": "subscribed",
            "station_id": station_id,
            "message": f"Subscribed to live stream for {station_id}",
        })
    except Exception:
        pass

    try:
        while True:
            # Drain any messages from frontend (keep-alive pings, etc.)
            # We don't process them, just keep the connection alive.
            await websocket.receive_text()
    except WebSocketDisconnect:
        log.info("Stream WS disconnect: station=%s client=%s", station_id, client_id)
    except Exception as exc:
        log.debug("Stream WS error: station=%s client=%s  %s", station_id, client_id, exc)
    finally:
        await stream_manager.unsubscribe(station_id, client_id)


@router.get("/subscribers")
async def get_subscriber_counts() -> dict:
    """Return live subscriber count per station (diagnostic endpoint)."""
    return stream_manager.all_subscriber_counts()

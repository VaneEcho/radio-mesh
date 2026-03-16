"""
Audio Stream Router
===================
Frontend clients subscribe here to receive demodulated audio chunks
forwarded from edge stations running an IF Analysis task.

WebSocket endpoint
------------------
WS /api/v1/audio/{station_id}/ws

    Protocol (server → client only):

    {"type":         "audio_chunk",
     "station_id":   "<id>",
     "timestamp_ms": <int>,
     "sample_rate":  <int>,
     "channels":     1,
     "encoding":     "pcm_s16le",
     "pcm_b64":      "<base64(PCM bytes)>"}

    {"type":       "subscribed",
     "station_id": "<id>",
     "message":    "Subscribed to audio stream"}

Time alignment
--------------
Every audio_chunk carries a ``timestamp_ms`` that matches the
``timestamp_ms`` of the contemporaneous stream_frame from the same
station.  Clients should buffer audio and schedule playback so that
audio playback position corresponds to the displayed spectrum timestamp.

REST endpoint
-------------
GET /api/v1/audio/subscribers
    Returns current subscriber counts per station (diagnostic).
"""
from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..audio_manager import audio_manager

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/audio", tags=["audio"])


@router.websocket("/{station_id}/ws")
async def frontend_audio_ws(websocket: WebSocket, station_id: str) -> None:
    """
    Frontend subscribes here to receive live audio chunks for one station.

    The connection is receive-only from the frontend's perspective.
    The frontend may send any text to keep the connection alive; the server
    ignores incoming messages.
    """
    await websocket.accept()
    client_id = str(uuid.uuid4())[:8]
    log.info("Audio WS connect: station=%s client=%s", station_id, client_id)

    await audio_manager.subscribe(station_id, websocket, client_id)

    try:
        await websocket.send_json({
            "type":       "subscribed",
            "station_id": station_id,
            "message":    f"Subscribed to audio stream for {station_id}",
        })
    except Exception:
        pass

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        log.info("Audio WS disconnect: station=%s client=%s", station_id, client_id)
    except Exception as exc:
        log.debug("Audio WS error: station=%s client=%s  %s", station_id, client_id, exc)
    finally:
        await audio_manager.unsubscribe(station_id, client_id)


@router.get("/subscribers")
async def get_audio_subscriber_counts() -> dict:
    """Return live audio subscriber count per station (diagnostic endpoint)."""
    return audio_manager.all_subscriber_counts()

"""
Station registration and WebSocket heartbeat.

REST endpoints
--------------
POST /api/v1/stations/register
    Edge calls this once on startup.  Creates or updates the station record.

GET  /api/v1/stations
    Returns all registered stations with online status.

WebSocket endpoint
------------------
WS /api/v1/stations/{station_id}/ws
    Persistent heartbeat channel.  Protocol:

    Edge → Cloud  every 30 s:  {"type": "ping", "ts": <unix_ms>}
    Cloud → Edge  immediately:  {"type": "pong", "ts": <unix_ms>}

    On connect  : station marked online.
    On disconnect: station marked offline.

    Cloud may also push commands to Edge over this channel in future phases:
    Cloud → Edge:  {"type": "cmd", "action": "task_start", "task_id": "..."}
"""
from __future__ import annotations

import asyncio
import json
import logging
import time

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from .. import db
from ..connection_manager import manager
from ..models import StationOut, StationRegisterAck, StationRegisterIn
from ..stream_manager import stream_manager

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/stations", tags=["stations"])


# ── REST: register ────────────────────────────────────────────────────────────

@router.post("/register", response_model=StationRegisterAck)
async def register_station(body: StationRegisterIn) -> StationRegisterAck:
    """
    Called by an edge node on startup.

    Inserts the station into the DB if new, or updates the name if it already
    exists.  Safe to call repeatedly (idempotent).
    """
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, db.upsert_station, body.station_id, body.name)
    return StationRegisterAck(station_id=body.station_id)


# ── REST: list stations ───────────────────────────────────────────────────────

@router.get("", response_model=list[StationOut])
async def get_stations() -> list[StationOut]:
    """Return all registered stations with their current online status."""
    loop = asyncio.get_running_loop()
    rows = await loop.run_in_executor(None, db.list_stations)
    return [StationOut(**r) for r in rows]


# ── WebSocket: heartbeat ──────────────────────────────────────────────────────

@router.websocket("/{station_id}/ws")
async def station_ws(websocket: WebSocket, station_id: str) -> None:
    """
    Persistent heartbeat channel for a single edge station.

    Connection lifecycle
    --------------------
    1. Edge connects → Cloud marks station online.
    2. Edge sends {"type": "ping", "ts": <ms>} every ~30 s.
    3. Cloud replies {"type": "pong", "ts": <ms>} and updates last_seen in DB.
    4. Edge disconnects (or network drops) → Cloud marks station offline.

    The DB update on every ping is intentionally lightweight (single UPDATE).
    For high-frequency scenarios, buffer in memory and flush periodically.
    """
    await websocket.accept()
    log.info("WS connect: station=%s", station_id)

    loop = asyncio.get_running_loop()
    now_ms = lambda: int(time.time() * 1000)

    # Register in connection manager (for task dispatch)
    await manager.connect(station_id, websocket)

    # Mark online on connect
    await loop.run_in_executor(
        None, db.set_station_online, station_id, True, now_ms()
    )

    try:
        while True:
            raw = await websocket.receive_text()

            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                log.warning("WS bad JSON from %s: %r", station_id, raw[:120])
                continue

            mtype = msg.get("type")

            if mtype == "ping":
                ts = now_ms()
                asyncio.ensure_future(
                    loop.run_in_executor(
                        None, db.set_station_online, station_id, True, ts
                    )
                )
                await websocket.send_text(json.dumps({"type": "pong", "ts": ts}))
                log.debug("WS ping/pong: station=%s", station_id)

            elif mtype == "task_ack":
                # Edge acknowledged receipt of a task and is starting execution
                task_id = msg.get("task_id")
                if task_id:
                    log.info("WS task_ack: station=%s task=%s", station_id, task_id)

            elif mtype == "task_progress":
                # Edge reporting incremental progress (optional)
                log.debug(
                    "WS task_progress: station=%s task=%s progress=%s%%",
                    station_id, msg.get("task_id"), msg.get("progress", "?"),
                )

            elif mtype == "stream_frame":
                # Edge is pushing a live spectrum frame; relay to frontend subscribers
                if stream_manager.subscriber_count(station_id) > 0:
                    asyncio.ensure_future(stream_manager.broadcast(station_id, msg))
                    log.debug("WS stream_frame relay: station=%s", station_id)

            else:
                log.debug("WS unknown msg from %s: type=%s", station_id, mtype)

    except WebSocketDisconnect:
        log.info("WS disconnect: station=%s", station_id)
    except Exception as exc:
        log.error("WS error: station=%s  %s", station_id, exc)
    finally:
        await manager.disconnect(station_id)
        await loop.run_in_executor(
            None, db.set_station_online, station_id, False, now_ms()
        )
        log.info("WS closed: station=%s marked offline", station_id)

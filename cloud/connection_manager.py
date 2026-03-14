"""
WebSocket Connection Manager
============================
Tracks the single active WebSocket per station.
Used to push task commands from Cloud → Edge over the heartbeat channel.

The connection_manager singleton is imported by both stations.py (to register
connections) and tasks.py (to dispatch tasks).
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional

from fastapi import WebSocket

log = logging.getLogger(__name__)


class ConnectionManager:
    """Registry of active edge WebSocket connections (one per station)."""

    def __init__(self) -> None:
        self._connections: dict[str, WebSocket] = {}
        self._lock = asyncio.Lock()

    async def connect(self, station_id: str, ws: WebSocket) -> None:
        async with self._lock:
            self._connections[station_id] = ws
        log.info("CM connect: %s  (total=%d)", station_id, len(self._connections))

    async def disconnect(self, station_id: str) -> None:
        async with self._lock:
            self._connections.pop(station_id, None)
        log.info("CM disconnect: %s  (total=%d)", station_id, len(self._connections))

    async def send(self, station_id: str, payload: dict) -> bool:
        """
        Push a JSON message to an edge station.

        Returns True if the message was sent, False if the station has no
        active connection.
        """
        async with self._lock:
            ws = self._connections.get(station_id)
        if ws is None:
            log.warning("CM.send: no connection for station %s", station_id)
            return False
        try:
            await ws.send_text(json.dumps(payload))
            log.debug("CM.send → %s: %s", station_id, payload.get("type", "?"))
            return True
        except Exception as exc:
            log.error("CM.send to %s failed: %s", station_id, exc)
            return False

    def is_connected(self, station_id: str) -> bool:
        return station_id in self._connections

    def connected_stations(self) -> list[str]:
        return list(self._connections.keys())


# ── Singleton ─────────────────────────────────────────────────────────────────

manager = ConnectionManager()

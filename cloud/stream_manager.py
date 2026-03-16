"""
Real-time Stream Manager
========================
Tracks frontend WebSocket subscribers for live spectrum streaming.

Each edge station broadcasts its frames to all connected frontend clients
that have subscribed to that station's stream.

Architecture
------------
Edge → Cloud station WS (stream_frame msg)
     → StreamManager.broadcast(station_id, payload)
     → all subscribed frontend WebSockets for that station

Usage
-----
    from .stream_manager import stream_manager

    # Subscribe a frontend client
    await stream_manager.subscribe(station_id, ws, client_id)

    # Broadcast a frame to all subscribers of a station
    await stream_manager.broadcast(station_id, payload_dict)

    # Unsubscribe on disconnect
    await stream_manager.unsubscribe(station_id, client_id)
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import NamedTuple

from fastapi import WebSocket

log = logging.getLogger(__name__)


class _Subscriber(NamedTuple):
    client_id: str
    ws: WebSocket


class StreamManager:
    """Registry of frontend WebSocket subscribers, keyed by station_id."""

    def __init__(self) -> None:
        # station_id → list of subscribers
        self._subs: dict[str, list[_Subscriber]] = {}
        self._lock = asyncio.Lock()

    async def subscribe(self, station_id: str, ws: WebSocket, client_id: str) -> None:
        async with self._lock:
            self._subs.setdefault(station_id, []).append(_Subscriber(client_id, ws))
        log.info(
            "Stream subscribe: station=%s client=%s  (total=%d)",
            station_id, client_id, self._count(station_id),
        )

    async def unsubscribe(self, station_id: str, client_id: str) -> None:
        async with self._lock:
            subs = self._subs.get(station_id, [])
            self._subs[station_id] = [s for s in subs if s.client_id != client_id]
        log.info("Stream unsubscribe: station=%s client=%s", station_id, client_id)

    async def broadcast(self, station_id: str, payload: dict) -> int:
        """
        Send payload to all subscribers of station_id.

        Returns the number of clients successfully reached.
        """
        async with self._lock:
            subs = list(self._subs.get(station_id, []))

        if not subs:
            return 0

        text = json.dumps(payload)
        sent = 0
        dead: list[str] = []

        for sub in subs:
            try:
                await sub.ws.send_text(text)
                sent += 1
            except Exception as exc:
                log.debug("Stream broadcast drop client=%s: %s", sub.client_id, exc)
                dead.append(sub.client_id)

        # Clean up dead connections
        if dead:
            async with self._lock:
                self._subs[station_id] = [
                    s for s in self._subs.get(station_id, [])
                    if s.client_id not in dead
                ]

        return sent

    def subscriber_count(self, station_id: str) -> int:
        return self._count(station_id)

    def all_subscriber_counts(self) -> dict[str, int]:
        return {sid: len(subs) for sid, subs in self._subs.items() if subs}

    def _count(self, station_id: str) -> int:
        return len(self._subs.get(station_id, []))


# ── Singleton ─────────────────────────────────────────────────────────────────

stream_manager = StreamManager()

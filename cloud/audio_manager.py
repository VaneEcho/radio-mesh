"""
Audio Stream Manager
====================
Mirrors stream_manager.py but for audio chunks.

Architecture
------------
Edge → Cloud station WS (audio_chunk msg)
     → AudioManager.broadcast(station_id, payload)
     → all subscribed frontend WebSockets for that station

Message format (server → frontend)
-----------------------------------
{
    "type":         "audio_chunk",
    "station_id":   "<id>",
    "timestamp_ms": <int>,       # UTC ms, must align with stream_frame timestamps
    "sample_rate":  <int>,       # e.g. 16000
    "channels":     <int>,       # 1 (mono)
    "encoding":     "pcm_s16le", # little-endian signed 16-bit PCM
    "pcm_b64":      "<base64>"   # base64-encoded raw PCM bytes
}

Usage
-----
    from .audio_manager import audio_manager

    await audio_manager.subscribe(station_id, ws, client_id)
    await audio_manager.broadcast(station_id, payload)
    await audio_manager.unsubscribe(station_id, client_id)
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


class AudioManager:
    """Registry of frontend WebSocket subscribers for audio streams."""

    def __init__(self) -> None:
        self._subs: dict[str, list[_Subscriber]] = {}
        self._lock = asyncio.Lock()

    async def subscribe(self, station_id: str, ws: WebSocket, client_id: str) -> None:
        async with self._lock:
            self._subs.setdefault(station_id, []).append(_Subscriber(client_id, ws))
        log.info(
            "Audio subscribe: station=%s client=%s (total=%d)",
            station_id, client_id, self._count(station_id),
        )

    async def unsubscribe(self, station_id: str, client_id: str) -> None:
        async with self._lock:
            subs = self._subs.get(station_id, [])
            self._subs[station_id] = [s for s in subs if s.client_id != client_id]
        log.info("Audio unsubscribe: station=%s client=%s", station_id, client_id)

    async def broadcast(self, station_id: str, payload: dict) -> int:
        """
        Send audio_chunk payload to all frontend subscribers of station_id.
        Returns count of clients successfully reached.
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
                log.debug("Audio broadcast drop client=%s: %s", sub.client_id, exc)
                dead.append(sub.client_id)

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

audio_manager = AudioManager()

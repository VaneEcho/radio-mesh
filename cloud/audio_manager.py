"""
Audio Stream Manager
====================
Tracks frontend WebSocket subscribers for live audio streams.

Mirrors stream_manager.py but for audio_chunk messages.
Supports the same dual backend: in-memory (default) or Redis pub/sub.

Channel name per station: ``audio:<station_id>``

Message format (server → frontend)
-----------------------------------
{
    "type":         "audio_chunk",
    "station_id":   "<id>",
    "timestamp_ms": <int>,       # UTC ms, aligned with stream_frame timestamps
    "sample_rate":  <int>,       # e.g. 16000
    "channels":     <int>,       # 1 (mono)
    "encoding":     "pcm_s16le", # little-endian signed 16-bit PCM
    "pcm_b64":      "<base64>"   # base64-encoded raw PCM bytes
}

Usage
-----
    from .audio_manager import audio_manager

    await audio_manager.init(redis_url="redis://localhost:6379/0")
    await audio_manager.subscribe(station_id, ws, client_id)
    await audio_manager.broadcast(station_id, payload)
    await audio_manager.unsubscribe(station_id, client_id)
    await audio_manager.close()
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

        self._redis = None
        self._pubsub = None
        self._listener_task: asyncio.Task | None = None
        self._channel_prefix = "audio"

    # ── Initialisation ────────────────────────────────────────────────────────

    async def init(self, redis_url: str | None = None) -> None:
        if redis_url:
            await self._init_redis(redis_url)
        else:
            log.info("AudioManager: using in-memory backend")

    async def _init_redis(self, redis_url: str) -> None:
        try:
            import redis.asyncio as aioredis
        except ImportError:
            log.error("redis package not installed — AudioManager using memory backend")
            return

        self._redis = aioredis.from_url(redis_url, decode_responses=True)
        try:
            await self._redis.ping()
        except Exception as exc:
            log.error("Redis ping failed for AudioManager (%s) — using memory backend", exc)
            self._redis = None
            return

        self._pubsub = self._redis.pubsub()
        await self._pubsub.psubscribe(f"{self._channel_prefix}:*")
        self._listener_task = asyncio.create_task(self._redis_listener())
        log.info("AudioManager: Redis backend active (%s)", redis_url)

    async def close(self) -> None:
        if self._listener_task:
            self._listener_task.cancel()
        if self._pubsub:
            try:
                await self._pubsub.close()
            except Exception:
                pass
        if self._redis:
            try:
                await self._redis.aclose()
            except Exception:
                pass

    # ── Public API ────────────────────────────────────────────────────────────

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
        if self._redis is not None:
            channel = f"{self._channel_prefix}:{station_id}"
            await self._redis.publish(channel, json.dumps(payload))
            return -1
        else:
            return await self._local_broadcast(station_id, payload)

    def subscriber_count(self, station_id: str) -> int:
        return self._count(station_id)

    def all_subscriber_counts(self) -> dict[str, int]:
        return {sid: len(subs) for sid, subs in self._subs.items() if subs}

    # ── Internal ──────────────────────────────────────────────────────────────

    async def _local_broadcast(self, station_id: str, payload: dict) -> int:
        async with self._lock:
            subs = list(self._subs.get(station_id, []))

        if not subs:
            return 0

        text = json.dumps(payload) if not isinstance(payload, str) else payload
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

    async def _redis_listener(self) -> None:
        log.info("AudioManager: Redis listener task started")
        try:
            async for msg in self._pubsub.listen():
                if msg["type"] != "pmessage":
                    continue
                try:
                    channel: str = msg["channel"]
                    station_id = channel[len(self._channel_prefix) + 1:]
                    data = json.loads(msg["data"])
                    await self._local_broadcast(station_id, data)
                except Exception as exc:
                    log.debug("AudioManager Redis listener error: %s", exc)
        except asyncio.CancelledError:
            log.info("AudioManager: Redis listener task cancelled")
        except Exception as exc:
            log.error("AudioManager: Redis listener crashed: %s", exc)

    def _count(self, station_id: str) -> int:
        return len(self._subs.get(station_id, []))


# ── Singleton ─────────────────────────────────────────────────────────────────

audio_manager = AudioManager()

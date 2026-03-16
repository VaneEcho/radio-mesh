"""
Real-time Stream Manager
========================
Tracks frontend WebSocket subscribers for live spectrum streaming.

Supports two backends, selected via the ``STREAM_BACKEND`` environment variable:

``memory`` (default)
    In-process dict.  Works with a single uvicorn worker.  No extra deps.

``redis``
    Uses Redis pub/sub.  Works across multiple uvicorn workers / replicas.
    Requires: ``redis[hiredis]>=5.0``, ``REDIS_URL`` env var.
    The channel name per station is ``stream:<station_id>``.

Architecture (both backends)
-----------------------------
Edge → Cloud station WS (stream_frame msg)
     → StreamManager.broadcast(station_id, payload)
     → all subscribed frontend WebSockets for that station

Usage
-----
    from .stream_manager import stream_manager

    # init (call once at startup, before accepting requests)
    await stream_manager.init(redis_url="redis://localhost:6379/0")  # or None

    # subscribe a frontend client
    await stream_manager.subscribe(station_id, ws, client_id)

    # broadcast a frame to all subscribers
    await stream_manager.broadcast(station_id, payload_dict)

    # on disconnect
    await stream_manager.unsubscribe(station_id, client_id)

    # clean up at shutdown
    await stream_manager.close()
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
    """
    Registry of frontend WebSocket subscribers for spectrum stream.

    Dual-backend: in-memory (single worker) or Redis pub/sub (multi-worker).
    """

    def __init__(self) -> None:
        # In-memory subscriber registry (local to this process)
        self._subs: dict[str, list[_Subscriber]] = {}
        self._lock = asyncio.Lock()

        # Redis state (None when memory backend is active)
        self._redis = None          # redis.asyncio.Redis
        self._pubsub = None         # redis.asyncio.client.PubSub
        self._listener_task: asyncio.Task | None = None
        self._channel_prefix = "stream"

    # ── Initialisation ────────────────────────────────────────────────────────

    async def init(self, redis_url: str | None = None) -> None:
        """
        Initialise the manager.  Call once at application startup.

        Parameters
        ----------
        redis_url:
            If provided, enables the Redis backend (e.g. ``redis://localhost:6379/0``).
            If None, the in-memory backend is used.
        """
        if redis_url:
            await self._init_redis(redis_url)
        else:
            log.info("StreamManager: using in-memory backend (single-worker mode)")

    async def _init_redis(self, redis_url: str) -> None:
        try:
            import redis.asyncio as aioredis
        except ImportError:
            log.error(
                "redis package not installed — falling back to memory backend. "
                "Run: pip install redis[hiredis]"
            )
            return

        self._redis = aioredis.from_url(redis_url, decode_responses=True)
        try:
            await self._redis.ping()
        except Exception as exc:
            log.error("Redis ping failed (%s) — falling back to memory backend", exc)
            self._redis = None
            return

        self._pubsub = self._redis.pubsub()
        await self._pubsub.psubscribe(f"{self._channel_prefix}:*")
        self._listener_task = asyncio.create_task(self._redis_listener())
        log.info("StreamManager: Redis backend active (%s)", redis_url)

    async def close(self) -> None:
        """Clean up Redis connections.  Call at application shutdown."""
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
            "Stream subscribe: station=%s client=%s (total=%d)",
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

        Redis backend: publishes to Redis channel; the listener task (running
        on every worker) picks it up and forwards to local WS connections.

        Memory backend: sends directly to all local WS connections.

        Returns -1 (unknown) for Redis backend; actual count for memory backend.
        """
        if self._redis is not None:
            channel = f"{self._channel_prefix}:{station_id}"
            await self._redis.publish(channel, json.dumps(payload))
            return -1  # count unknown in multi-worker mode
        else:
            return await self._local_broadcast(station_id, payload)

    def subscriber_count(self, station_id: str) -> int:
        return self._count(station_id)

    def all_subscriber_counts(self) -> dict[str, int]:
        return {sid: len(subs) for sid, subs in self._subs.items() if subs}

    # ── Internal ──────────────────────────────────────────────────────────────

    async def _local_broadcast(self, station_id: str, payload: dict) -> int:
        """Send payload directly to all local WS connections for station_id."""
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
                log.debug("Stream broadcast drop client=%s: %s", sub.client_id, exc)
                dead.append(sub.client_id)

        if dead:
            async with self._lock:
                self._subs[station_id] = [
                    s for s in self._subs.get(station_id, [])
                    if s.client_id not in dead
                ]

        return sent

    async def _redis_listener(self) -> None:
        """
        Background task: read from Redis pubsub and forward to local WS connections.

        One listener per worker process.  Every worker receives every published
        message and forwards only to its own local subscribers.
        """
        log.info("StreamManager: Redis listener task started")
        try:
            async for msg in self._pubsub.listen():
                if msg["type"] != "pmessage":
                    continue
                try:
                    channel: str = msg["channel"]
                    station_id = channel[len(self._channel_prefix) + 1:]  # strip "stream:"
                    data = json.loads(msg["data"])
                    await self._local_broadcast(station_id, data)
                except Exception as exc:
                    log.debug("StreamManager Redis listener error: %s", exc)
        except asyncio.CancelledError:
            log.info("StreamManager: Redis listener task cancelled")
        except Exception as exc:
            log.error("StreamManager: Redis listener crashed: %s", exc)

    def _count(self, station_id: str) -> int:
        return len(self._subs.get(station_id, []))


# ── Singleton ─────────────────────────────────────────────────────────────────

stream_manager = StreamManager()

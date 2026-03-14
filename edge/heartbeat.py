"""
Edge Heartbeat — registration and WebSocket keep-alive.

Runs in a daemon thread so it does not block the scan loop.

Lifecycle
---------
1. Call register() once via HTTP POST /api/v1/stations/register.
2. Open WebSocket WS /api/v1/stations/{station_id}/ws.
3. Send {"type": "ping", "ts": <ms>} every PING_INTERVAL_S seconds.
4. On any error / disconnect: wait with exponential back-off, then retry
   from step 1 (re-register + reconnect).

Task handling
-------------
When Cloud pushes {"type": "task", ...} over the WebSocket, the message is
placed onto task_queue so the Scanner can pick it up.  The heartbeat thread
immediately sends back {"type": "task_ack", "task_id": ...} to inform Cloud
that the message was received.

Usage
-----
    tq = queue.Queue()
    hb = Heartbeat(cfg=cfg, task_queue=tq)
    hb.start()          # non-blocking, starts daemon thread
    ...
    hb.stop()           # signals thread to exit on next loop
"""
from __future__ import annotations

import json
import logging
import queue
import threading
import time
from typing import Optional

import requests
import websocket  # websocket-client

log = logging.getLogger(__name__)

PING_INTERVAL_S: float = 30.0
_BACKOFF_BASE_S: float = 5.0
_BACKOFF_MAX_S: float = 60.0


class Heartbeat:
    """
    Background heartbeat thread.

    Parameters
    ----------
    cfg : dict
        Parsed config.yaml.
    task_queue : queue.Queue, optional
        Incoming task messages from Cloud are put here for the Scanner.
    """

    def __init__(self, cfg: dict, task_queue: Optional[queue.Queue] = None) -> None:
        self._station_id: str = cfg["station"]["id"]
        self._station_name: str = cfg["station"].get("name", self._station_id)

        cloud_cfg = cfg.get("cloud", {})
        self._enabled: bool = cloud_cfg.get("enabled", False)
        self._base_url: str = cloud_cfg.get("url", "http://localhost:8000").rstrip("/")
        self._token: str = cloud_cfg.get("token", "")

        self._task_queue = task_queue
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._ws: Optional[websocket.WebSocket] = None  # for sending task_ack

    # ── Public API ────────────────────────────────────────────────────────────

    def start(self) -> None:
        if not self._enabled:
            log.info("Heartbeat disabled (cloud.enabled=false) — skipping")
            return
        self._thread = threading.Thread(
            target=self._run, name="heartbeat", daemon=True,
        )
        self._thread.start()
        log.info("Heartbeat thread started (station=%s → %s)", self._station_id, self._base_url)

    def stop(self) -> None:
        self._stop_event.set()

    # ── Internal ──────────────────────────────────────────────────────────────

    def _run(self) -> None:
        backoff = _BACKOFF_BASE_S
        while not self._stop_event.is_set():
            try:
                self._register()
                self._run_ws()          # blocks until disconnect
                backoff = _BACKOFF_BASE_S
            except Exception as exc:
                log.warning("Heartbeat error: %s — retry in %.0f s", exc, backoff)
                self._stop_event.wait(timeout=backoff)
                backoff = min(backoff * 2, _BACKOFF_MAX_S)
        log.info("Heartbeat thread exiting")

    def _register(self) -> None:
        url = f"{self._base_url}/api/v1/stations/register"
        payload = {"station_id": self._station_id, "name": self._station_name}
        log.info("Registering station %s at %s …", self._station_id, url)
        resp = requests.post(url, json=payload, headers=self._auth_headers(), timeout=10)
        resp.raise_for_status()
        log.info("Registration OK")

    def _run_ws(self) -> None:
        ws_base = self._base_url.replace("http://", "ws://").replace("https://", "wss://")
        ws_url = f"{ws_base}/api/v1/stations/{self._station_id}/ws"
        log.info("WS connecting to %s", ws_url)

        ws = websocket.create_connection(
            ws_url, timeout=10, header=self._ws_headers(),
        )
        self._ws = ws
        log.info("WS connected")

        try:
            while not self._stop_event.is_set():
                ts = int(time.time() * 1000)
                ws.send(json.dumps({"type": "ping", "ts": ts}))
                log.debug("WS ping sent")

                ws.settimeout(10)
                try:
                    raw = ws.recv()
                    self._handle_message(ws, raw)
                except websocket.WebSocketTimeoutException:
                    log.warning("WS pong timeout — reconnecting")
                    break

                self._stop_event.wait(timeout=PING_INTERVAL_S)
        finally:
            self._ws = None
            try:
                ws.close()
            except Exception:
                pass
            log.info("WS closed")

    def _handle_message(self, ws: websocket.WebSocket, raw: str) -> None:
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            log.warning("WS bad JSON: %r", raw[:80])
            return

        mtype = msg.get("type")

        if mtype == "pong":
            log.debug("WS pong received")

        elif mtype == "task":
            task_id = msg.get("task_id", "?")
            log.info("WS received task: id=%s type=%s", task_id, msg.get("task_type"))
            # Acknowledge immediately so Cloud knows we got it
            try:
                ws.send(json.dumps({"type": "task_ack", "task_id": task_id}))
            except Exception as exc:
                log.warning("Failed to send task_ack: %s", exc)
            # Hand off to Scanner via queue
            if self._task_queue is not None:
                self._task_queue.put(msg)
            else:
                log.warning("Task received but no task_queue — dropped: %s", task_id)

        else:
            log.debug("WS unknown message type: %s", mtype)

    def _auth_headers(self) -> dict:
        if self._token:
            return {"Authorization": f"Bearer {self._token}"}
        return {}

    def _ws_headers(self) -> list[str]:
        if self._token:
            return [f"Authorization: Bearer {self._token}"]
        return []

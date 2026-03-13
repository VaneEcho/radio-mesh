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

Usage
-----
    hb = Heartbeat(cfg=cfg)
    hb.start()          # non-blocking, starts daemon thread
    ...
    hb.stop()           # signals thread to exit on next loop
"""
from __future__ import annotations

import json
import logging
import threading
import time
from typing import Optional

import requests
import websocket  # websocket-client

log = logging.getLogger(__name__)

PING_INTERVAL_S: float = 30.0   # how often to ping Cloud
_BACKOFF_BASE_S: float = 5.0    # initial retry wait
_BACKOFF_MAX_S: float = 60.0    # maximum retry wait


class Heartbeat:
    """
    Background heartbeat thread.

    Parameters
    ----------
    cfg : dict
        Parsed config.yaml.  Reads:
          station.id, station.name
          cloud.enabled, cloud.url, cloud.token
    """

    def __init__(self, cfg: dict) -> None:
        self._station_id: str = cfg["station"]["id"]
        self._station_name: str = cfg["station"].get("name", self._station_id)

        cloud_cfg = cfg.get("cloud", {})
        self._enabled: bool = cloud_cfg.get("enabled", False)
        self._base_url: str = cloud_cfg.get("url", "http://localhost:8000").rstrip("/")
        self._token: str = cloud_cfg.get("token", "")

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # ── Public API ────────────────────────────────────────────────────────

    def start(self) -> None:
        """Start the heartbeat daemon thread."""
        if not self._enabled:
            log.info("Heartbeat disabled (cloud.enabled=false) — skipping")
            return
        self._thread = threading.Thread(
            target=self._run,
            name="heartbeat",
            daemon=True,
        )
        self._thread.start()
        log.info("Heartbeat thread started (station=%s → %s)", self._station_id, self._base_url)

    def stop(self) -> None:
        """Signal the heartbeat thread to exit."""
        self._stop_event.set()

    # ── Internal ──────────────────────────────────────────────────────────

    def _run(self) -> None:
        """Main loop: register → connect WS → ping.  Retries on any failure."""
        backoff = _BACKOFF_BASE_S

        while not self._stop_event.is_set():
            try:
                self._register()
                self._run_ws()          # blocks until disconnect
                backoff = _BACKOFF_BASE_S  # reset on clean disconnect
            except Exception as exc:
                log.warning("Heartbeat error: %s — retry in %.0f s", exc, backoff)
                self._stop_event.wait(timeout=backoff)
                backoff = min(backoff * 2, _BACKOFF_MAX_S)

        log.info("Heartbeat thread exiting")

    def _register(self) -> None:
        """
        POST /api/v1/stations/register

        Tells Cloud this station exists.  Safe to call multiple times
        (Cloud does an upsert).
        """
        url = f"{self._base_url}/api/v1/stations/register"
        headers = self._auth_headers()
        payload = {"station_id": self._station_id, "name": self._station_name}

        log.info("Registering station %s at %s …", self._station_id, url)
        resp = requests.post(url, json=payload, headers=headers, timeout=10)
        resp.raise_for_status()
        log.info("Registration OK: %s", resp.json())

    def _run_ws(self) -> None:
        """
        Open WebSocket and send pings until the connection drops or stop() is called.

        websocket-client is synchronous, which is fine here because we're in a
        dedicated thread.  We set a socket timeout so a dead server doesn't
        block forever.
        """
        ws_url = self._base_url.replace("http://", "ws://").replace("https://", "wss://")
        ws_url = f"{ws_url}/api/v1/stations/{self._station_id}/ws"

        log.info("WS connecting to %s", ws_url)
        ws = websocket.create_connection(
            ws_url,
            timeout=10,
            header=self._ws_headers(),
        )
        log.info("WS connected")

        try:
            while not self._stop_event.is_set():
                ts = int(time.time() * 1000)
                ws.send(json.dumps({"type": "ping", "ts": ts}))
                log.debug("WS ping sent (ts=%d)", ts)

                # Wait for pong (with timeout so we can check stop_event)
                ws.settimeout(10)
                try:
                    raw = ws.recv()
                    msg = json.loads(raw)
                    if msg.get("type") == "pong":
                        log.debug("WS pong received (ts=%d)", msg.get("ts", 0))
                except websocket.WebSocketTimeoutException:
                    log.warning("WS pong timeout — reconnecting")
                    break

                # Wait before next ping, but wake up early if stop() is called
                self._stop_event.wait(timeout=PING_INTERVAL_S)

        finally:
            try:
                ws.close()
            except Exception:
                pass
            log.info("WS closed")

    def _auth_headers(self) -> dict:
        if self._token:
            return {"Authorization": f"Bearer {self._token}"}
        return {}

    def _ws_headers(self) -> list[str]:
        if self._token:
            return [f"Authorization: Bearer {self._token}"]
        return []

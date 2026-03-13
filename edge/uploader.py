"""
Bundle Uploader
===============
Receives AggregatedBundles from the aggregator and either:
  A) POSTs them to the Cloud REST API  (cloud.enabled = true)
  B) Writes them as JSON files locally  (cloud.enabled = false, debug mode)

Runs in a background daemon thread so upload latency never blocks the scan loop.
A simple in-memory queue (max 120 bundles ≈ 2 hours) acts as a buffer for
short network outages.  On overflow the oldest bundle is dropped with a warning.

Upload retry: 3 attempts with 5 s / 15 s / 30 s back-off.
"""
from __future__ import annotations

import json
import logging
import queue
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .models import AggregatedBundle

log = logging.getLogger(__name__)

_QUEUE_MAX = 120        # max buffered bundles
_RETRY_DELAYS = (5, 15, 30)  # seconds between retry attempts


class Uploader:
    """
    Background uploader thread.

    Parameters
    ----------
    cloud_enabled : bool
        True  → HTTP upload to cloud_url + upload_path
        False → write JSON to output_dir
    cloud_url : str
        Base URL of the Cloud server (e.g. "http://192.168.1.200:8000").
    upload_path : str
        REST endpoint path (e.g. "/api/v1/spectrum/bundle").
    token : str
        Bearer token for Cloud authentication.
    output_dir : str | Path
        Directory for local debug output (used when cloud_enabled=False).
    """

    def __init__(
        self,
        cloud_enabled: bool = False,
        cloud_url: str = "http://localhost:8000",
        upload_path: str = "/api/v1/spectrum/bundle",
        token: str = "",
        output_dir: str | Path = "./output",
    ) -> None:
        self._cloud_enabled = cloud_enabled
        self._upload_url = cloud_url.rstrip("/") + upload_path
        self._token = token
        self._output_dir = Path(output_dir)

        self._queue: queue.Queue[AggregatedBundle] = queue.Queue(maxsize=_QUEUE_MAX)
        self._thread = threading.Thread(
            target=self._worker, name="uploader", daemon=True
        )
        self._stop_event = threading.Event()

    def start(self) -> None:
        if self._cloud_enabled:
            log.info("Uploader: cloud mode → %s", self._upload_url)
        else:
            self._output_dir.mkdir(parents=True, exist_ok=True)
            log.info("Uploader: local-file mode → %s", self._output_dir.resolve())
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._thread.join(timeout=10)

    def submit(self, bundle: AggregatedBundle) -> None:
        """
        Enqueue a bundle for upload.  Non-blocking: if the queue is full the
        oldest entry is dropped to make room.
        """
        try:
            self._queue.put_nowait(bundle)
        except queue.Full:
            try:
                dropped = self._queue.get_nowait()
                log.warning(
                    "Uploader queue full — dropped bundle from %s",
                    _ts_str(dropped.period_start_ms),
                )
            except queue.Empty:
                pass
            self._queue.put_nowait(bundle)

    # ── Worker thread ────────────────────────────────────────────────────

    def _worker(self) -> None:
        while not self._stop_event.is_set():
            try:
                bundle = self._queue.get(timeout=2.0)
            except queue.Empty:
                continue

            if self._cloud_enabled:
                self._upload_with_retry(bundle)
            else:
                self._write_local(bundle)

            self._queue.task_done()

    def _upload_with_retry(self, bundle: AggregatedBundle) -> None:
        import urllib.request
        import urllib.error

        payload = json.dumps(bundle.to_dict()).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._token}",
        }

        for attempt, delay in enumerate([0] + list(_RETRY_DELAYS), start=1):
            if delay:
                time.sleep(delay)
            try:
                req = urllib.request.Request(
                    self._upload_url, data=payload, headers=headers, method="POST"
                )
                with urllib.request.urlopen(req, timeout=15) as resp:
                    status = resp.status
                if status in (200, 201, 204):
                    log.info(
                        "Uploaded bundle %s (%d channels) → HTTP %d",
                        _ts_str(bundle.period_start_ms),
                        len(bundle.channels),
                        status,
                    )
                    return
                log.warning(
                    "Upload attempt %d/%d: HTTP %d for bundle %s",
                    attempt, len(_RETRY_DELAYS) + 1,
                    status, _ts_str(bundle.period_start_ms),
                )
            except Exception as exc:
                log.warning(
                    "Upload attempt %d/%d failed for bundle %s: %s",
                    attempt, len(_RETRY_DELAYS) + 1,
                    _ts_str(bundle.period_start_ms), exc,
                )

        # All retries exhausted — save locally as fallback
        log.error(
            "All upload attempts failed for bundle %s — saving locally",
            _ts_str(bundle.period_start_ms),
        )
        self._write_local(bundle)

    def _write_local(self, bundle: AggregatedBundle) -> None:
        ts = datetime.fromtimestamp(
            bundle.period_start_ms / 1000, tz=timezone.utc
        )
        filename = (
            f"{bundle.station_id}_{ts.strftime('%Y%m%dT%H%M%SZ')}.json"
        )
        path = self._output_dir / filename
        try:
            path.write_text(
                json.dumps(bundle.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            log.info(
                "Bundle saved locally: %s (%d channels)",
                filename, len(bundle.channels),
            )
        except OSError as exc:
            log.error("Failed to write bundle %s: %s", filename, exc)


def _ts_str(ms: int) -> str:
    """Format a Unix-ms timestamp as a short UTC string for log messages."""
    dt = datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
    return dt.strftime("%H:%M:%S")

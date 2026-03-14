"""
Main Scan Loop
==============
Orchestrates the continuous spectrum monitoring cycle:

  while True:
    0. Check task_queue for pending tasks from Cloud; execute if present
    1. Call driver.band_scan() → SpectrumFrame
    2. Pass frame to aggregator.update()
    3. aggregator.tick() → fires SpectrumBundle every interval_s
    4. (bundle handed to uploader via on_bundle callback)
    5. Log progress

Task execution
--------------
When a task arrives via the heartbeat WebSocket, the Scanner pauses the
background scan, executes the task using the driver, and reports the result
back to Cloud via HTTP POST /api/v1/tasks/{task_id}/results.

The loop is intentionally synchronous and single-threaded.  Upload happens
in a separate daemon thread (Uploader).  Graceful shutdown on SIGINT/SIGTERM.
"""
from __future__ import annotations

import base64
import gzip
import json
import logging
import queue
import signal
import time
import urllib.error
import urllib.request
from types import FrameType
from typing import Optional

import numpy as np

from .aggregator import Aggregator
from .drivers import EM550Driver, MockDriver, BaseSpectrumDriver
from .models import SpectrumBundle
from .uploader import Uploader

log = logging.getLogger(__name__)


def _build_driver(cfg: dict) -> BaseSpectrumDriver:
    dev = cfg["device"]
    dtype = dev.get("type", "em550").lower()

    if dtype == "em550":
        return EM550Driver(
            host=dev["host"],
            port=int(dev.get("port", 5555)),
            timeout_ms=int(dev.get("timeout_ms", 60_000)),
            default_step_hz=float(dev.get("step_hz", 25_000)),
            detector=dev.get("detector", "PAVerage"),
            synth_mode=dev.get("synth_mode", "FAST"),
            dwell_s=float(dev.get("dwell_s", 0.001)),
            agc=bool(dev.get("agc", True)),
            mgc_dbuv=float(dev.get("mgc_dbuv", 50.0)),
        )

    if dtype == "rsa306b":
        from .drivers import RSA306BDriver
        return RSA306BDriver()

    if dtype == "mock":
        return MockDriver(
            scan_delay_s=float(dev.get("scan_delay_s", 0.0)),
            seed=dev.get("seed", None),
        )

    raise ValueError(f"Unknown device type: {dtype!r}")


class Scanner:
    """
    Continuous spectrum scanner.

    Parameters
    ----------
    cfg : dict
        Parsed config.yaml content.
    uploader : Uploader
        Running uploader instance.
    task_queue : queue.Queue, optional
        Tasks pushed here by the Heartbeat thread.
    """

    def __init__(
        self,
        cfg: dict,
        uploader: Uploader,
        task_queue: Optional[queue.Queue] = None,
    ) -> None:
        self._cfg = cfg
        self._uploader = uploader
        self._task_queue = task_queue or queue.Queue()

        station_id = cfg["station"]["id"]
        agg_interval = float(cfg.get("aggregation", {}).get("interval_s", 60.0))

        self._aggregator = Aggregator(
            station_id=station_id,
            interval_s=agg_interval,
            on_bundle=self._on_bundle,
        )

        scan_cfg = cfg.get("scan", {})
        self._start_hz = float(scan_cfg.get("start_hz", 20e6))
        self._stop_hz  = float(scan_cfg.get("stop_hz", 3600e6))
        self._step_hz  = float(cfg["device"].get("step_hz", 25_000))

        cloud_cfg = cfg.get("cloud", {})
        self._cloud_url = cloud_cfg.get("url", "http://localhost:8000").rstrip("/")
        self._cloud_token = cloud_cfg.get("token", "")
        self._cloud_enabled = cloud_cfg.get("enabled", False)

        self._dump_raw = cfg.get("debug", {}).get("dump_raw_frames", False)
        self._station_id = station_id

        self._running = False
        self._sweep_count = 0

    def run(self) -> None:
        self._running = True
        self._register_signals()

        driver = _build_driver(self._cfg)
        log.info("Connecting to device …")

        with driver:
            log.info("Device connected: %r", driver)
            log.info(
                "Scan range: %.1f – %.1f MHz, step %.0f Hz",
                self._start_hz / 1e6, self._stop_hz / 1e6, self._step_hz,
            )

            while self._running:
                # ── Check for cloud-dispatched tasks ───────────────────────
                self._drain_tasks(driver)
                # ── Normal background sweep ────────────────────────────────
                self._sweep(driver)

        remaining = self._aggregator.flush()
        if remaining:
            self._uploader.submit(remaining)
        log.info("Scanner stopped after %d sweeps.", self._sweep_count)

    def stop(self) -> None:
        log.info("Scanner: stop requested")
        self._running = False

    # ── Task execution ────────────────────────────────────────────────────────

    def _drain_tasks(self, driver: BaseSpectrumDriver) -> None:
        """Execute all pending tasks before the next background sweep."""
        while True:
            try:
                task_msg = self._task_queue.get_nowait()
            except queue.Empty:
                break
            self._execute_task(driver, task_msg)

    def _execute_task(self, driver: BaseSpectrumDriver, msg: dict) -> None:
        task_id   = msg.get("task_id", "UNKNOWN")
        task_type = msg.get("task_type", "")
        params    = msg.get("params", {})

        log.info("Executing task %s (type=%s)", task_id, task_type)
        t0 = time.monotonic()

        result_b64 = None
        result_meta = None
        error = None

        try:
            if task_type == "band_scan":
                frame = driver.band_scan(
                    start_hz=float(params.get("start_hz", self._start_hz)),
                    stop_hz=float(params.get("stop_hz", self._stop_hz)),
                    step_hz=float(params.get("step_hz", self._step_hz)),
                    station_id=self._station_id,
                )
                result_b64, result_meta = _encode_frame(frame)

            elif task_type == "channel_scan":
                step_hz = float(params["step_hz"])
                frame = driver.channel_scan(
                    start_hz=float(params["start_hz"]),
                    stop_hz=float(params["stop_hz"]),
                    step_hz=step_hz,
                    demod_bw_hz=float(params.get("demod_bw_hz", step_hz * 0.8)),
                    station_id=self._station_id,
                )
                result_b64, result_meta = _encode_frame(frame)

            elif task_type == "if_analysis":
                if_frame = driver.if_analysis(
                    center_hz=float(params["center_hz"]),
                    span_hz=float(params.get("span_hz", 200_000)),
                    station_id=self._station_id,
                )
                result_b64, result_meta = _encode_frame(if_frame)

            else:
                error = f"Unknown task type: {task_type!r}"

        except Exception as exc:
            error = str(exc)
            log.exception("Task %s execution failed", task_id)

        elapsed = time.monotonic() - t0
        log.info(
            "Task %s done in %.1f s: %s",
            task_id, elapsed, "error: " + error if error else "OK",
        )

        # Report result back to cloud
        if self._cloud_enabled:
            self._report_result(task_id, result_b64, result_meta, error)

    def _report_result(
        self,
        task_id: str,
        result_b64: Optional[str],
        result_meta: Optional[dict],
        error: Optional[str],
    ) -> None:
        url = f"{self._cloud_url}/api/v1/tasks/{task_id}/results"
        payload = json.dumps({
            "station_id": self._station_id,
            "result_b64": result_b64,
            "result_meta": result_meta,
            "error": error,
        }).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._cloud_token}",
        }
        for attempt in range(3):
            try:
                req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
                with urllib.request.urlopen(req, timeout=15) as resp:
                    if resp.status in (200, 201, 204):
                        log.info("Task %s result reported successfully", task_id)
                        return
            except Exception as exc:
                log.warning("Report result attempt %d failed: %s", attempt + 1, exc)
                time.sleep(5 * (attempt + 1))
        log.error("All attempts to report task %s result failed", task_id)

    # ── Background scan ───────────────────────────────────────────────────────

    def _sweep(self, driver: BaseSpectrumDriver) -> None:
        t0 = time.monotonic()
        try:
            frame = driver.band_scan(
                start_hz=self._start_hz,
                stop_hz=self._stop_hz,
                step_hz=self._step_hz,
                station_id=self._station_id,
            )
        except Exception as exc:
            log.error("Sweep failed: %s — retrying in 5 s", exc)
            time.sleep(5)
            return

        elapsed = time.monotonic() - t0
        self._sweep_count += 1
        log.debug(
            "Sweep #%d: %d pts, %.1f–%.1f MHz in %.1f s",
            self._sweep_count, frame.num_points,
            frame.freq_start_hz / 1e6, frame.freq_stop_hz / 1e6, elapsed,
        )

        if self._dump_raw:
            _dump_frame(frame, self._cfg.get("debug", {}).get("output_dir", "./output"))

        self._aggregator.update(frame)
        self._aggregator.tick()

    def _on_bundle(self, bundle: SpectrumBundle) -> None:
        log.info(
            "Bundle ready: station=%s bins=%d sweeps=%d",
            bundle.station_id, bundle.num_points, bundle.sweep_count,
        )
        self._uploader.submit(bundle)

    def _register_signals(self) -> None:
        def _handler(sig: int, _frame: Optional[FrameType]) -> None:
            log.info("Signal %d — stopping …", sig)
            self.stop()

        signal.signal(signal.SIGINT, _handler)
        signal.signal(signal.SIGTERM, _handler)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _encode_frame(frame) -> tuple[str, dict]:
    """Encode a SpectrumFrame to base64(gzip(float32[])) + metadata dict."""
    arr = np.array(frame.levels_dbm, dtype=np.float32)
    compressed = gzip.compress(arr.tobytes(), compresslevel=6)
    b64 = base64.b64encode(compressed).decode("ascii")
    meta = {
        "freq_start_hz": frame.freq_start_hz,
        "freq_step_hz":  frame.freq_step_hz,
        "num_points":    frame.num_points,
    }
    return b64, meta


def _dump_frame(frame, output_dir: str) -> None:
    import json as _json
    from datetime import datetime, timezone
    from pathlib import Path

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    ts = datetime.fromtimestamp(frame.timestamp_ms / 1000, tz=timezone.utc)
    fname = f"frame_{ts.strftime('%Y%m%dT%H%M%S%fZ')}.json"
    data = {
        "station_id": frame.station_id,
        "timestamp_ms": frame.timestamp_ms,
        "freq_start_hz": frame.freq_start_hz,
        "freq_step_hz": frame.freq_step_hz,
        "num_points": frame.num_points,
        "levels_dbm": frame.levels_dbm.tolist(),
    }
    (out / fname).write_text(_json.dumps(data), encoding="utf-8")
    log.debug("Raw frame written: %s", fname)

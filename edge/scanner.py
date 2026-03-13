"""
Main Scan Loop
==============
Orchestrates the continuous spectrum monitoring cycle:

  while True:
    1. Call driver.band_scan() → SpectrumFrame
    2. Pass frame to aggregator.update()
    3. aggregator.tick() → fires SpectrumBundle every interval_s
    4. (bundle handed to uploader via on_bundle callback)
    5. Log progress

The loop is intentionally synchronous and single-threaded.  Upload happens
in a separate daemon thread (Uploader).  Graceful shutdown on SIGINT/SIGTERM.
"""
from __future__ import annotations

import logging
import signal
import time
from types import FrameType
from typing import Optional

from .aggregator import Aggregator
from .drivers import EM550Driver, MockDriver, BaseSpectrumDriver
from .models import SpectrumBundle
from .uploader import Uploader

log = logging.getLogger(__name__)


def _build_driver(cfg: dict) -> BaseSpectrumDriver:
    """Instantiate the correct driver from config."""
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
    """

    def __init__(
        self,
        cfg: dict,
        uploader: Uploader,
    ) -> None:
        self._cfg = cfg
        self._uploader = uploader

        station_id = cfg["station"]["id"]
        agg_interval = float(cfg.get("aggregation", {}).get("interval_s", 60.0))

        self._aggregator = Aggregator(
            station_id=station_id,
            interval_s=agg_interval,
            on_bundle=self._on_bundle,
        )

        self._scan_cfg = cfg.get("scan", {})
        self._start_hz = float(self._scan_cfg.get("start_hz", 20e6))
        self._stop_hz = float(self._scan_cfg.get("stop_hz", 3600e6))
        self._step_hz = float(cfg["device"].get("step_hz", 25_000))

        self._dump_raw = cfg.get("debug", {}).get("dump_raw_frames", False)

        self._running = False
        self._sweep_count = 0

    def run(self) -> None:
        """
        Start the scan loop.  Blocks until stop() is called or a fatal error
        occurs.  Registers SIGINT / SIGTERM handlers for graceful shutdown.
        """
        self._running = True
        self._register_signals()

        driver = _build_driver(self._cfg)
        log.info("Connecting to device …")

        with driver:
            log.info("Device connected: %r", driver)
            log.info(
                "Scan range: %.1f – %.1f MHz, step %.0f Hz",
                self._start_hz / 1e6,
                self._stop_hz / 1e6,
                self._step_hz,
            )

            while self._running:
                self._sweep(driver)

        # Flush any remaining data on clean exit
        remaining = self._aggregator.flush()
        if remaining:
            self._uploader.submit(remaining)
        log.info("Scanner stopped after %d sweeps.", self._sweep_count)

    def stop(self) -> None:
        """Signal the scan loop to stop after the current sweep finishes."""
        log.info("Scanner: stop requested")
        self._running = False

    # ── Internal ─────────────────────────────────────────────────────────

    def _sweep(self, driver: BaseSpectrumDriver) -> None:
        """Execute one full band scan and update the aggregator."""
        t0 = time.monotonic()

        try:
            frame = driver.band_scan(
                start_hz=self._start_hz,
                stop_hz=self._stop_hz,
                step_hz=self._step_hz,
                station_id=self._cfg["station"]["id"],
            )
        except Exception as exc:
            log.error("Sweep failed: %s — retrying in 5 s", exc)
            time.sleep(5)
            return

        elapsed = time.monotonic() - t0
        self._sweep_count += 1

        log.debug(
            "Sweep #%d: %d pts, %.1f – %.1f MHz in %.1f s",
            self._sweep_count,
            frame.num_points,
            frame.freq_start_hz / 1e6,
            frame.freq_stop_hz / 1e6,
            elapsed,
        )

        if self._dump_raw:
            _dump_frame(frame, self._cfg.get("debug", {}).get("output_dir", "./output"))

        self._aggregator.update(frame)
        self._aggregator.tick()

    def _on_bundle(self, bundle: SpectrumBundle) -> None:
        """Called by aggregator when a 1-minute window closes."""
        log.info(
            "Bundle ready: station=%s period=%s bins=%d sweeps=%d",
            bundle.station_id,
            _period_str(bundle),
            bundle.num_points,
            bundle.sweep_count,
        )
        self._uploader.submit(bundle)

    def _register_signals(self) -> None:
        def _handler(sig: int, _frame: Optional[FrameType]) -> None:
            log.info("Received signal %d — stopping …", sig)
            self.stop()

        signal.signal(signal.SIGINT, _handler)
        signal.signal(signal.SIGTERM, _handler)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _period_str(bundle: SpectrumBundle) -> str:
    from datetime import datetime, timezone
    start = datetime.fromtimestamp(bundle.period_start_ms / 1000, tz=timezone.utc)
    end = datetime.fromtimestamp(bundle.period_end_ms / 1000, tz=timezone.utc)
    return f"{start.strftime('%H:%M:%S')}–{end.strftime('%H:%M:%S')} UTC"


def _dump_frame(frame, output_dir: str) -> None:
    """Write a raw SpectrumFrame to a JSON file for debugging."""
    import json
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
    (out / fname).write_text(json.dumps(data), encoding="utf-8")
    log.debug("Raw frame written: %s", fname)

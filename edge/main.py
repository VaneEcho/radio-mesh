"""
RF·MESH Edge Agent — Entry Point
=================================
Usage:
    cd edge/
    python main.py                        # uses ./config.yaml by default
    python main.py --config /path/to/cfg  # explicit config path
    python main.py --help
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import yaml


def _setup_logging(level: str = "INFO") -> None:
    fmt = "%(asctime)s  %(levelname)-8s  %(name)s  %(message)s"
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format=fmt,
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def _load_config(path: Path) -> dict:
    if not path.exists():
        print(f"ERROR: Config file not found: {path}", file=sys.stderr)
        print(
            f"Copy the template first:  cp config.yaml.template config.yaml",
            file=sys.stderr,
        )
        sys.exit(1)
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="RF·MESH Edge Agent — continuous spectrum monitor"
    )
    parser.add_argument(
        "--config", "-c",
        default="config.yaml",
        metavar="PATH",
        help="Path to config.yaml (default: ./config.yaml)",
    )
    parser.add_argument(
        "--log-level", "-l",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity (default: INFO)",
    )
    args = parser.parse_args()

    _setup_logging(args.log_level)
    log = logging.getLogger("edge.main")

    cfg_path = Path(args.config)
    log.info("Loading config: %s", cfg_path.resolve())
    cfg = _load_config(cfg_path)

    station_id = cfg["station"]["id"]
    station_name = cfg["station"].get("name", station_id)
    log.info("Station: %s (%s)", station_name, station_id)

    # ── Uploader ──────────────────────────────────────────────────────────
    from .uploader import Uploader

    cloud_cfg = cfg.get("cloud", {})
    debug_cfg = cfg.get("debug", {})

    uploader = Uploader(
        cloud_enabled=cloud_cfg.get("enabled", False),
        cloud_url=cloud_cfg.get("url", "http://localhost:8000"),
        upload_path=cloud_cfg.get("upload_path", "/api/v1/spectrum/bundle"),
        token=cloud_cfg.get("token", ""),
        output_dir=debug_cfg.get("output_dir", "./output"),
    )
    uploader.start()

    # ── Scanner ───────────────────────────────────────────────────────────
    from .scanner import Scanner

    scanner = Scanner(cfg=cfg, uploader=uploader)

    log.info("Starting scan loop …  (Ctrl-C to stop)")
    try:
        scanner.run()
    finally:
        uploader.stop()
        log.info("Edge agent shut down cleanly.")


if __name__ == "__main__":
    main()

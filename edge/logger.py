"""
RF·MESH Edge — Structured JSON logging setup.

Call ``setup_logging()`` once at startup (in edge/main.py) before any other
imports that use logging.  All subsequent ``logging.getLogger(name)`` calls
will automatically emit one JSON object per line, compatible with ELK/Loki.

Log rotation
------------
Logs are written to ``logs/edge.log`` relative to the *current working
directory*, rotated daily, with 30 days of history kept.

Environment variables
---------------------
LOG_DIR   Override the log directory (default: ``./logs``)
"""
from __future__ import annotations

import json
import logging
import logging.handlers
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


class _JsonFormatter(logging.Formatter):
    """Single-line JSON log record formatter."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "ts":     datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level":  record.levelname,
            "module": record.name,
            "msg":    record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        # Include any extra fields attached by callers (e.g. station_id, task_id)
        for key, val in record.__dict__.items():
            if key not in (
                "name", "msg", "args", "levelname", "levelno",
                "pathname", "filename", "module", "exc_info", "exc_text",
                "stack_info", "lineno", "funcName", "created", "msecs",
                "relativeCreated", "thread", "threadName", "processName",
                "process", "message", "taskName",
            ):
                if not key.startswith("_"):
                    try:
                        json.dumps(val)   # only include JSON-serialisable extras
                        payload[key] = val
                    except TypeError:
                        payload[key] = repr(val)
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(level: str = "INFO", log_dir: str | None = None) -> None:
    """
    Configure root logger to emit structured JSON logs.

    Parameters
    ----------
    level:   Log level string (DEBUG / INFO / WARNING / ERROR).
    log_dir: Directory for the rotating file handler.
             Defaults to the ``LOG_DIR`` env var or ``./logs``.
    """
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    formatter = _JsonFormatter()

    handlers: list[logging.Handler] = []

    # ── Console handler (stdout) ───────────────────────────────────────────────
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    handlers.append(console)

    # ── Rotating file handler ──────────────────────────────────────────────────
    _log_dir = Path(log_dir or os.environ.get("LOG_DIR", "./logs"))
    try:
        _log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.TimedRotatingFileHandler(
            filename=_log_dir / "edge.log",
            when="midnight",
            backupCount=30,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        handlers.append(file_handler)
    except OSError as exc:
        # Non-fatal: if we can't write logs to disk, keep console only.
        print(f"WARNING: Cannot open log file in {_log_dir}: {exc}", file=sys.stderr)

    logging.basicConfig(level=numeric_level, handlers=handlers, force=True)

    # Suppress noisy third-party loggers
    logging.getLogger("websocket").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

"""
RF·MESH Cloud Backend — FastAPI application entry point.

Start with:
    uvicorn cloud.main:app --host 0.0.0.0 --port 8000 --reload

Or via Docker Compose:
    docker compose up

Environment variables
---------------------
DATABASE_URL          PostgreSQL DSN (default: postgresql://rfmesh:rfmesh@localhost:5432/rfmesh)
API_TOKEN             Bearer token required on all write endpoints (empty = no auth)
LOG_LEVEL             DEBUG / INFO / WARNING (default: INFO)
LOG_DIR               Directory for rotating log files (default: ./logs)
DATA_RETENTION_DAYS   Days of spectrum history to keep (default: 90; 0 = disabled)
"""
from __future__ import annotations

import asyncio
import json
import logging
import logging.handlers
import os
import sys
import time
from datetime import timezone
from pathlib import Path

from fastapi import FastAPI, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware

from . import db
from .audio_manager import audio_manager
from .stream_manager import stream_manager
from .routers import (
    analysis, audio, band_rules, freq_assign, ingest, query,
    signals, stations, stream, tasks,
)

# ── Structured JSON logging ───────────────────────────────────────────────────

class _JsonFormatter(logging.Formatter):
    """Single-line JSON log record formatter."""
    def format(self, record: logging.LogRecord) -> str:
        from datetime import datetime
        payload = {
            "ts":     datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level":  record.levelname,
            "module": record.name,
            "msg":    record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def _setup_logging() -> None:
    level_str = os.environ.get("LOG_LEVEL", "INFO").upper()
    numeric_level = getattr(logging, level_str, logging.INFO)
    formatter = _JsonFormatter()

    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]

    log_dir = Path(os.environ.get("LOG_DIR", "./logs"))
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        fh = logging.handlers.TimedRotatingFileHandler(
            filename=log_dir / "cloud.log",
            when="midnight",
            backupCount=30,
            encoding="utf-8",
        )
        fh.setFormatter(formatter)
        handlers.append(fh)
    except OSError as exc:
        print(f"WARNING: Cannot open cloud log file in {log_dir}: {exc}", file=sys.stderr)

    for h in handlers:
        h.setFormatter(formatter)

    logging.basicConfig(level=numeric_level, handlers=handlers, force=True)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


_setup_logging()
log = logging.getLogger("cloud.main")

# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="RF·MESH Cloud API",
    version="0.1.0",
    description=(
        "Multi-station radio spectrum monitoring backend.  "
        "Receives compressed spectrum bundles from edge agents, "
        "stores them in TimescaleDB, and exposes query + band-rule CRUD APIs."
    ),
)

# Allow the frontend (any origin for now; tighten in production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Simple token auth middleware ──────────────────────────────────────────────

_API_TOKEN = os.environ.get("API_TOKEN", "").strip()
_WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
_AUTH_EXEMPT_PATHS = {"/", "/health", "/docs", "/redoc", "/openapi.json"}


@app.middleware("http")
async def token_auth(request: Request, call_next) -> Response:
    """
    Bearer-token authentication for all write operations.

    - If API_TOKEN env var is empty → no auth required (dev mode).
    - If API_TOKEN is set → all POST/PUT/PATCH/DELETE requests must supply
      a matching ``Authorization: Bearer <token>`` header, except the paths
      listed in _AUTH_EXEMPT_PATHS.
    """
    if _API_TOKEN and request.method in _WRITE_METHODS:
        if request.url.path not in _AUTH_EXEMPT_PATHS:
            header = request.headers.get("Authorization", "")
            if not header.startswith("Bearer "):
                return Response(
                    content='{"detail":"Missing Authorization header"}',
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    media_type="application/json",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            provided = header[len("Bearer "):]
            if provided != _API_TOKEN:
                log.warning(
                    "Auth rejected: method=%s path=%s",
                    request.method, request.url.path,
                )
                return Response(
                    content='{"detail":"Invalid token"}',
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    media_type="application/json",
                    headers={"WWW-Authenticate": "Bearer"},
                )
    return await call_next(request)


# ── Lifespan ──────────────────────────────────────────────────────────────────

_DATA_RETENTION_DAYS = int(os.environ.get("DATA_RETENTION_DAYS", "90"))
_STREAM_BACKEND = os.environ.get("STREAM_BACKEND", "memory").lower()
_REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

_expiry_task: asyncio.Task | None = None
_retention_task: asyncio.Task | None = None


async def _task_expiry_loop() -> None:
    """Background loop: expire stale tasks every 5 minutes."""
    while True:
        await asyncio.sleep(300)  # 5 minutes
        try:
            loop = asyncio.get_running_loop()
            n = await loop.run_in_executor(None, db.expire_stale_tasks, 30)
            if n:
                log.info("Background: expired %d stale task(s)", n)
        except Exception:
            log.exception("Task expiry loop error")


async def _retention_loop() -> None:
    """Background loop: delete spectrum frames older than DATA_RETENTION_DAYS, once per day."""
    if _DATA_RETENTION_DAYS <= 0:
        log.info("Data retention disabled (DATA_RETENTION_DAYS=0)")
        return
    log.info("Data retention enabled: keeping %d days of spectrum history", _DATA_RETENTION_DAYS)
    while True:
        await asyncio.sleep(86400)  # 24 hours
        try:
            cutoff_ms = int((time.time() - _DATA_RETENTION_DAYS * 86400) * 1000)
            loop = asyncio.get_running_loop()
            n = await loop.run_in_executor(None, db.delete_old_frames, cutoff_ms)
            log.info("Data retention: removed %d spectrum frame(s)", n)
        except Exception:
            log.exception("Data retention loop error")


@app.on_event("startup")
async def startup() -> None:
    global _expiry_task, _retention_task
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, db.init_pool)
    await loop.run_in_executor(None, db.init_schema)

    # Init stream managers (Redis backend if configured)
    redis_url = _REDIS_URL if _STREAM_BACKEND == "redis" else None
    await stream_manager.init(redis_url=redis_url)
    await audio_manager.init(redis_url=redis_url)
    if redis_url:
        log.info("Stream backend: Redis (%s)", redis_url)
    else:
        log.info("Stream backend: in-memory (single-worker mode)")

    _expiry_task = asyncio.create_task(_task_expiry_loop())
    _retention_task = asyncio.create_task(_retention_loop())
    log.info("RF·MESH Cloud API ready")


@app.on_event("shutdown")
async def shutdown() -> None:
    global _expiry_task, _retention_task
    for t in (_expiry_task, _retention_task):
        if t:
            t.cancel()
    await stream_manager.close()
    await audio_manager.close()
    db.close_pool()
    log.info("RF·MESH Cloud API shut down")


# ── Routers ───────────────────────────────────────────────────────────────────

app.include_router(ingest.router)
app.include_router(query.router)
app.include_router(band_rules.router)
app.include_router(stations.router)
app.include_router(tasks.router)
app.include_router(freq_assign.router)
app.include_router(stream.router)
app.include_router(audio.router)
app.include_router(analysis.router)
app.include_router(signals.router)


# ── Health / root ─────────────────────────────────────────────────────────────

@app.get("/health", tags=["meta"])
async def health() -> dict:
    return {"status": "ok"}


@app.get("/", tags=["meta"])
async def root() -> dict:
    return {
        "service": "RF·MESH Cloud API",
        "version": "0.1.0",
        "docs": "/docs",
    }

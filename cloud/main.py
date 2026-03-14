"""
RF·MESH Cloud Backend — FastAPI application entry point.

Start with:
    uvicorn cloud.main:app --host 0.0.0.0 --port 8000 --reload

Or via Docker Compose:
    docker compose up

Environment variables
---------------------
DATABASE_URL   PostgreSQL DSN (default: postgresql://rfmesh:rfmesh@localhost:5432/rfmesh)
API_TOKEN      Bearer token required on all write endpoints (optional; empty = no auth)
LOG_LEVEL      DEBUG / INFO / WARNING (default: INFO)
"""
from __future__ import annotations

import logging
import os

from fastapi import FastAPI, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware

from . import db
from .routers import band_rules, freq_assign, ingest, query, stations, tasks

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
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

_API_TOKEN = os.environ.get("API_TOKEN", "")
_WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
_AUTH_EXEMPT_PATHS = {"/", "/health", "/docs", "/redoc", "/openapi.json"}


@app.middleware("http")
async def token_auth(request: Request, call_next) -> Response:
    if _API_TOKEN and request.method in _WRITE_METHODS:
        if request.url.path not in _AUTH_EXEMPT_PATHS:
            header = request.headers.get("Authorization", "")
            if not header.startswith("Bearer ") or header[7:] != _API_TOKEN:
                return Response(
                    content='{"detail":"Unauthorized"}',
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    media_type="application/json",
                )
    return await call_next(request)


# ── Lifespan ──────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup() -> None:
    import asyncio
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, db.init_pool)
    await loop.run_in_executor(None, db.init_schema)
    log.info("RF·MESH Cloud API ready")


@app.on_event("shutdown")
async def shutdown() -> None:
    db.close_pool()
    log.info("RF·MESH Cloud API shut down")


# ── Routers ───────────────────────────────────────────────────────────────────

app.include_router(ingest.router)
app.include_router(query.router)
app.include_router(band_rules.router)
app.include_router(stations.router)
app.include_router(tasks.router)
app.include_router(freq_assign.router)


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

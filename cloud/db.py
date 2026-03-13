"""
RF·MESH Cloud Backend — Database layer (TimescaleDB / PostgreSQL).

Uses plain psycopg2 (synchronous) wrapped in a thread pool via
asyncio.run_in_executor, so FastAPI async endpoints stay non-blocking.

TimescaleDB schema
------------------
spectrum_frames   — one row per station per 1-minute aggregation window.
                    The levels array is stored compressed as BYTEA.
band_rules        — configurable frequency band definitions (cloud-only).

Environment variables
---------------------
DATABASE_URL      Full PostgreSQL DSN:
                  postgresql://user:pass@host:5432/rfmesh
                  Defaults to: postgresql://rfmesh:rfmesh@localhost:5432/rfmesh
"""
from __future__ import annotations

import base64
import gzip
import logging
import os
import struct
from contextlib import contextmanager
from typing import Generator

import psycopg2
import psycopg2.extras
from psycopg2.pool import ThreadedConnectionPool

log = logging.getLogger(__name__)

_DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://rfmesh:rfmesh@localhost:5432/rfmesh",
)

_pool: ThreadedConnectionPool | None = None

# ── Connection pool ───────────────────────────────────────────────────────────

def init_pool(minconn: int = 2, maxconn: int = 10) -> None:
    global _pool
    _pool = ThreadedConnectionPool(minconn, maxconn, dsn=_DATABASE_URL)
    log.info("DB pool initialised: %s (min=%d max=%d)", _DATABASE_URL, minconn, maxconn)


def close_pool() -> None:
    if _pool:
        _pool.closeall()
        log.info("DB pool closed")


@contextmanager
def get_conn() -> Generator:
    if _pool is None:
        raise RuntimeError("DB pool not initialised — call init_pool() first")
    conn = _pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _pool.putconn(conn)


# ── Schema initialisation ─────────────────────────────────────────────────────

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS spectrum_frames (
    frame_id        BIGSERIAL PRIMARY KEY,
    station_id      TEXT        NOT NULL,
    period_start    TIMESTAMPTZ NOT NULL,
    period_end      TIMESTAMPTZ NOT NULL,
    period_start_ms BIGINT      NOT NULL,
    period_end_ms   BIGINT      NOT NULL,
    sweep_count     INT         NOT NULL,
    freq_start_hz   DOUBLE PRECISION NOT NULL,
    freq_step_hz    DOUBLE PRECISION NOT NULL,
    num_points      INT         NOT NULL,
    levels_gz       BYTEA       NOT NULL    -- gzip(float32[num_points])
);

SELECT create_hypertable(
    'spectrum_frames', 'period_start',
    if_not_exists => TRUE
);

CREATE INDEX IF NOT EXISTS ix_sf_station_time
    ON spectrum_frames (station_id, period_start DESC);

CREATE TABLE IF NOT EXISTS band_rules (
    rule_id       SERIAL PRIMARY KEY,
    name          TEXT    NOT NULL,
    freq_start_hz DOUBLE PRECISION NOT NULL,
    freq_stop_hz  DOUBLE PRECISION NOT NULL,
    service       TEXT    NOT NULL,
    authority     TEXT,
    notes         TEXT
);
"""

def init_schema() -> None:
    """Create tables and hypertable if they don't exist yet."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(_SCHEMA_SQL)
    log.info("DB schema ready")


# ── spectrum_frames ───────────────────────────────────────────────────────────

def insert_bundle(
    station_id: str,
    period_start_ms: int,
    period_end_ms: int,
    sweep_count: int,
    freq_start_hz: float,
    freq_step_hz: float,
    num_points: int,
    levels_dbm_b64: str,
) -> int:
    """
    Decode the base64(gzip(float32[])) payload and store it.
    Returns the assigned frame_id.
    """
    # Decode and re-compress (edge already gzips; we store the raw gzip bytes)
    compressed = base64.b64decode(levels_dbm_b64)
    # Validate: decompress then count floats
    raw = gzip.decompress(compressed)
    n = len(raw) // 4
    if n != num_points:
        log.warning(
            "insert_bundle: declared num_points=%d but decoded %d floats",
            num_points, n,
        )
        num_points = n

    sql = """
        INSERT INTO spectrum_frames
            (station_id, period_start, period_end,
             period_start_ms, period_end_ms, sweep_count,
             freq_start_hz, freq_step_hz, num_points, levels_gz)
        VALUES
            (%s,
             to_timestamp(%s::double precision / 1000),
             to_timestamp(%s::double precision / 1000),
             %s, %s, %s, %s, %s, %s, %s)
        RETURNING frame_id
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (
                station_id,
                period_start_ms, period_end_ms,
                period_start_ms, period_end_ms,
                sweep_count,
                freq_start_hz, freq_step_hz, num_points,
                psycopg2.Binary(compressed),
            ))
            frame_id = cur.fetchone()[0]

    log.info(
        "Stored frame_id=%d station=%s sweeps=%d bins=%d",
        frame_id, station_id, sweep_count, num_points,
    )
    return frame_id


def query_bundles(
    station_id: str,
    start_ms: int,
    end_ms: int,
    freq_start_hz: float | None = None,
    freq_stop_hz: float | None = None,
    limit: int = 500,
) -> list[dict]:
    """
    Return spectrum_frames rows for a station within a time window.
    levels_gz is re-encoded to base64 for the API response.
    """
    conditions = [
        "station_id = %s",
        "period_start_ms >= %s",
        "period_end_ms <= %s",
    ]
    params: list = [station_id, start_ms, end_ms]

    sql = f"""
        SELECT frame_id, station_id, period_start_ms, period_end_ms,
               sweep_count, freq_start_hz, freq_step_hz, num_points, levels_gz
        FROM spectrum_frames
        WHERE {' AND '.join(conditions)}
        ORDER BY period_start_ms
        LIMIT %s
    """
    params.append(limit)

    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()

    result = []
    for row in rows:
        gz_bytes = bytes(row["levels_gz"])
        b64 = base64.b64encode(gz_bytes).decode("ascii")
        result.append({
            "frame_id": row["frame_id"],
            "station_id": row["station_id"],
            "period_start_ms": row["period_start_ms"],
            "period_end_ms": row["period_end_ms"],
            "sweep_count": row["sweep_count"],
            "freq_start_hz": row["freq_start_hz"],
            "freq_step_hz": row["freq_step_hz"],
            "num_points": row["num_points"],
            "levels_dbm_b64": b64,
        })
    return result


# ── band_rules ────────────────────────────────────────────────────────────────

def list_band_rules() -> list[dict]:
    sql = """
        SELECT rule_id, name, freq_start_hz, freq_stop_hz, service, authority, notes
        FROM band_rules
        ORDER BY freq_start_hz
    """
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql)
            return [dict(r) for r in cur.fetchall()]


def create_band_rule(
    name: str,
    freq_start_hz: float,
    freq_stop_hz: float,
    service: str,
    authority: str | None,
    notes: str | None,
) -> int:
    sql = """
        INSERT INTO band_rules (name, freq_start_hz, freq_stop_hz, service, authority, notes)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING rule_id
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (name, freq_start_hz, freq_stop_hz, service, authority, notes))
            return cur.fetchone()[0]


def update_band_rule(rule_id: int, **fields) -> bool:
    allowed = {"name", "freq_start_hz", "freq_stop_hz", "service", "authority", "notes"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return False
    set_clause = ", ".join(f"{k} = %s" for k in updates)
    sql = f"UPDATE band_rules SET {set_clause} WHERE rule_id = %s"
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (*updates.values(), rule_id))
            return cur.rowcount > 0


def delete_band_rule(rule_id: int) -> bool:
    sql = "DELETE FROM band_rules WHERE rule_id = %s"
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (rule_id,))
            return cur.rowcount > 0

"""
RF·MESH Cloud Backend — Database layer (TimescaleDB / PostgreSQL).

Uses plain psycopg2 (synchronous) wrapped in a thread pool via
asyncio.run_in_executor, so FastAPI async endpoints stay non-blocking.

TimescaleDB schema
------------------
spectrum_frames   — one row per station per 1-minute aggregation window.
                    The levels array is stored compressed as BYTEA.
band_rules        — configurable frequency band definitions (cloud-only).
tasks             — task dispatch records (Cloud → Edge).
task_stations     — per-station status and result for each task.

Environment variables
---------------------
DATABASE_URL      Full PostgreSQL DSN:
                  postgresql://user:pass@host:5432/rfmesh
                  Defaults to: postgresql://rfmesh:rfmesh@localhost:5432/rfmesh
"""
from __future__ import annotations

import base64
import gzip
import json
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
    frame_id        BIGSERIAL   NOT NULL,
    station_id      TEXT        NOT NULL,
    period_start    TIMESTAMPTZ NOT NULL,
    period_end      TIMESTAMPTZ NOT NULL,
    period_start_ms BIGINT      NOT NULL,
    period_end_ms   BIGINT      NOT NULL,
    sweep_count     INT         NOT NULL,
    freq_start_hz   DOUBLE PRECISION NOT NULL,
    freq_step_hz    DOUBLE PRECISION NOT NULL,
    num_points      INT         NOT NULL,
    levels_gz       BYTEA       NOT NULL,   -- gzip(float32[num_points])
    PRIMARY KEY (frame_id, period_start)
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

-- Station registry: one row per edge node.
-- online / last_seen_ms are updated by the WebSocket heartbeat handler.
CREATE TABLE IF NOT EXISTS stations (
    station_id      TEXT PRIMARY KEY,
    name            TEXT        NOT NULL,
    registered_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_ms    BIGINT,
    online          BOOLEAN     NOT NULL DEFAULT FALSE
);

-- Task dispatch records.  Each task targets one or more stations.
CREATE TABLE IF NOT EXISTS tasks (
    task_id     TEXT PRIMARY KEY,
    type        TEXT        NOT NULL,   -- band_scan / channel_scan / if_analysis
    params      TEXT        NOT NULL,   -- JSON string
    stream_fps  INT         NOT NULL DEFAULT 0,
    status      TEXT        NOT NULL DEFAULT 'pending',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Per-station status and result for each task.
CREATE TABLE IF NOT EXISTS task_stations (
    task_id       TEXT        NOT NULL REFERENCES tasks(task_id),
    station_id    TEXT        NOT NULL,
    status        TEXT        NOT NULL DEFAULT 'pending',
    dispatched_at TIMESTAMPTZ,
    started_at    TIMESTAMPTZ,
    finished_at   TIMESTAMPTZ,
    result_b64    TEXT,   -- base64(gzip(float32[])) for band/channel scan
    result_meta   TEXT,   -- JSON metadata (freq_start_hz, freq_step_hz, …)
    error         TEXT,
    PRIMARY KEY (task_id, station_id)
);

CREATE INDEX IF NOT EXISTS ix_tasks_created ON tasks (created_at DESC);
CREATE INDEX IF NOT EXISTS ix_task_stations_station ON task_stations (station_id, task_id);

-- Signal analyses: results from local detection + optional AI
CREATE TABLE IF NOT EXISTS signal_analyses (
    analysis_id     BIGSERIAL PRIMARY KEY,
    station_id      TEXT NOT NULL,
    frame_id        BIGINT,
    freq_start_hz   DOUBLE PRECISION NOT NULL,
    freq_stop_hz    DOUBLE PRECISION NOT NULL,
    period_start_ms BIGINT NOT NULL,
    period_end_ms   BIGINT NOT NULL,
    threshold_dbm   DOUBLE PRECISION NOT NULL DEFAULT -90.0,
    detections      TEXT NOT NULL DEFAULT '[]',  -- JSON list of detected signals
    ai_summary      TEXT,                         -- AI-generated text (optional)
    ai_backend      TEXT,                         -- 'claude' / 'openai' / 'local'
    status          TEXT NOT NULL DEFAULT 'new',  -- new/confirmed/dismissed
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_analyses_station ON signal_analyses (station_id, created_at DESC);

-- Signal library: manually catalogued or AI-identified signals
CREATE TABLE IF NOT EXISTS signal_records (
    signal_id       BIGSERIAL PRIMARY KEY,
    name            TEXT NOT NULL,
    freq_center_hz  DOUBLE PRECISION NOT NULL,
    bandwidth_hz    DOUBLE PRECISION,
    modulation      TEXT,
    service         TEXT,
    authority       TEXT,
    station_id      TEXT,
    first_seen_ms   BIGINT,
    last_seen_ms    BIGINT,
    max_dbm         DOUBLE PRECISION,
    notes           TEXT,
    status          TEXT NOT NULL DEFAULT 'active',  -- active / archived
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_signals_freq ON signal_records (freq_center_hz);
"""

def init_schema() -> None:
    """Create tables and hypertable if they don't exist yet."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(_SCHEMA_SQL)
    log.info("DB schema ready")


def delete_old_frames(cutoff_ms: int) -> int:
    """
    Delete spectrum_frames older than *cutoff_ms* (Unix milliseconds).

    TimescaleDB drops whole chunks that fall entirely before the cutoff,
    making this operation very efficient for time-series data.

    Returns the number of rows deleted.
    """
    sql = "DELETE FROM spectrum_frames WHERE period_start_ms < %s"
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (cutoff_ms,))
            deleted = cur.rowcount
    if deleted:
        log.info("Data retention: deleted %d frame(s) older than cutoff_ms=%d", deleted, cutoff_ms)
    return deleted


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


# ── stations ──────────────────────────────────────────────────────────────────

def upsert_station(station_id: str, name: str) -> None:
    """
    Insert a new station or update its name if it already exists.
    Called when an edge node registers (or re-registers after restart).

    Uses INSERT … ON CONFLICT so it's safe to call repeatedly.
    """
    sql = """
        INSERT INTO stations (station_id, name, registered_at)
        VALUES (%s, %s, now())
        ON CONFLICT (station_id) DO UPDATE
            SET name = EXCLUDED.name
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (station_id, name))
    log.info("Station registered: %s (%s)", station_id, name)


def set_station_online(station_id: str, online: bool, last_seen_ms: int) -> None:
    """
    Update the online flag and last-seen timestamp.
    Called by the WebSocket heartbeat handler on each ping / disconnect.
    """
    sql = """
        UPDATE stations
        SET online = %s, last_seen_ms = %s
        WHERE station_id = %s
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (online, last_seen_ms, station_id))


def list_stations() -> list[dict]:
    """Return all registered stations ordered by station_id."""
    sql = """
        SELECT station_id, name, registered_at, last_seen_ms, online
        FROM stations
        ORDER BY station_id
    """
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql)
            return [dict(r) for r in cur.fetchall()]


# ── tasks ─────────────────────────────────────────────────────────────────────

def create_task(
    task_id: str,
    task_type: str,
    params: dict,
    station_ids: list[str],
    stream_fps: int = 0,
) -> None:
    """Insert a new task and its per-station placeholders."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO tasks (task_id, type, params, stream_fps, status)
                VALUES (%s, %s, %s, %s, 'pending')
                """,
                (task_id, task_type, json.dumps(params), stream_fps),
            )
            for sid in station_ids:
                cur.execute(
                    """
                    INSERT INTO task_stations (task_id, station_id, status)
                    VALUES (%s, %s, 'pending')
                    """,
                    (task_id, sid),
                )


def mark_task_dispatched(task_id: str, station_id: str) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE task_stations
                SET status = 'dispatched', dispatched_at = now()
                WHERE task_id = %s AND station_id = %s
                """,
                (task_id, station_id),
            )
            cur.execute(
                "UPDATE tasks SET status = 'dispatched', updated_at = now() WHERE task_id = %s",
                (task_id,),
            )


def save_task_result(
    task_id: str,
    station_id: str,
    result_b64: str | None,
    result_meta: dict | None,
    error: str | None,
) -> None:
    """Called when an edge agent reports task completion or failure."""
    status = "failed" if error else "completed"
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE task_stations
                SET status = %s, finished_at = now(),
                    result_b64 = %s, result_meta = %s, error = %s
                WHERE task_id = %s AND station_id = %s
                """,
                (
                    status,
                    result_b64,
                    json.dumps(result_meta) if result_meta else None,
                    error,
                    task_id, station_id,
                ),
            )
            # Update parent task status: completed if all stations done
            cur.execute(
                """
                UPDATE tasks SET updated_at = now(),
                    status = CASE
                        WHEN NOT EXISTS (
                            SELECT 1 FROM task_stations
                            WHERE task_id = %s
                              AND status NOT IN ('completed', 'failed')
                        ) THEN 'completed'
                        ELSE status
                    END
                WHERE task_id = %s
                """,
                (task_id, task_id),
            )


def get_task(task_id: str) -> dict | None:
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT t.task_id, t.type, t.params, t.stream_fps, t.status,
                       t.created_at, t.updated_at
                FROM tasks t
                WHERE t.task_id = %s
                """,
                (task_id,),
            )
            row = cur.fetchone()
            if row is None:
                return None
            task = dict(row)
            cur.execute(
                """
                SELECT station_id, status, dispatched_at, started_at,
                       finished_at, result_b64, result_meta, error
                FROM task_stations
                WHERE task_id = %s
                ORDER BY station_id
                """,
                (task_id,),
            )
            task["stations"] = [dict(r) for r in cur.fetchall()]
            return task


def list_tasks(limit: int = 100) -> list[dict]:
    sql = """
        SELECT task_id, type, status, created_at, updated_at,
               (SELECT COUNT(*) FROM task_stations ts WHERE ts.task_id = t.task_id) AS station_count,
               (SELECT COUNT(*) FROM task_stations ts WHERE ts.task_id = t.task_id AND ts.status = 'completed') AS completed_count
        FROM tasks t
        ORDER BY created_at DESC
        LIMIT %s
    """
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (limit,))
            return [dict(r) for r in cur.fetchall()]


# ── freq-timeseries ───────────────────────────────────────────────────────────

def query_freq_timeseries(
    freq_hz: float,
    start_ms: int,
    end_ms: int,
    station_ids: list[str] | None = None,
) -> list[dict]:
    """
    Extract the power level of a single frequency bin across all stations
    and all frames within the time window.

    For each matching frame, we:
      1. Decompress levels_gz → float32 array
      2. Compute bin_idx = round((freq_hz - freq_start_hz) / freq_step_hz)
      3. If 0 <= bin_idx < num_points, record (period_start_ms, dbm)

    Returns a list of dicts grouped by station_id, sorted by time.
    """
    import struct as _struct

    conditions = [
        "period_start_ms >= %s",
        "period_end_ms   <= %s",
        # Only frames whose freq range actually covers the requested freq
        "freq_start_hz <= %s",
        "(freq_start_hz + freq_step_hz * (num_points - 1)) >= %s",
    ]
    params: list = [start_ms, end_ms, freq_hz, freq_hz]

    if station_ids:
        placeholders = ",".join(["%s"] * len(station_ids))
        conditions.append(f"station_id IN ({placeholders})")
        params.extend(station_ids)

    sql = f"""
        SELECT station_id, period_start_ms, period_end_ms,
               freq_start_hz, freq_step_hz, num_points, levels_gz
        FROM spectrum_frames
        WHERE {' AND '.join(conditions)}
        ORDER BY station_id, period_start_ms
    """

    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()

    # Group by station, extract the bin
    per_station: dict[str, list] = {}
    for row in rows:
        sid = row["station_id"]
        bin_idx = round(
            (freq_hz - row["freq_start_hz"]) / row["freq_step_hz"]
        )
        if not (0 <= bin_idx < row["num_points"]):
            continue
        raw = gzip.decompress(bytes(row["levels_gz"]))
        # float32 little-endian
        dbm = _struct.unpack_from("<f", raw, bin_idx * 4)[0]
        per_station.setdefault(sid, []).append({
            "t": row["period_start_ms"],
            "dbm": round(float(dbm), 2),
        })

    return [
        {"station_id": sid, "series": points}
        for sid, points in per_station.items()
    ]


# ── freq-assign ───────────────────────────────────────────────────────────────

def query_channel_max_levels(
    station_id: str,
    start_hz: float,
    stop_hz: float,
    channel_bw_hz: float,
    lookback_ms: int,
) -> list[dict]:
    """
    Compute the maximum measured dBm within each channel of a given band,
    using all stored frames in the most recent `lookback_ms` window.

    Algorithm:
      1. Fetch all relevant frames from the DB.
      2. For each frame, decompress and extract the slice covering
         [start_hz, stop_hz].
      3. Aggregate per-channel max across all frames (channel width = channel_bw_hz).
      4. Return list of { channel_idx, center_hz, start_hz, stop_hz, max_dbm }.

    This runs in the DB thread pool (not async).
    """
    import struct as _struct
    import time as _time

    now_ms = int(_time.time() * 1000)
    from_ms = now_ms - lookback_ms

    # Only fetch frames whose freq range overlaps the requested band
    sql = """
        SELECT freq_start_hz, freq_step_hz, num_points, levels_gz
        FROM spectrum_frames
        WHERE station_id = %s
          AND period_start_ms >= %s
          AND freq_start_hz <= %s
          AND (freq_start_hz + freq_step_hz * (num_points - 1)) >= %s
        ORDER BY period_start_ms
    """
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (station_id, from_ms, stop_hz, start_hz))
            rows = cur.fetchall()

    if not rows:
        return []

    # Number of channels
    n_channels = max(1, int((stop_hz - start_hz) / channel_bw_hz))
    channel_max = [-999.0] * n_channels

    for row in rows:
        f0   = row["freq_start_hz"]
        fstep= row["freq_step_hz"]
        npts = row["num_points"]
        raw  = gzip.decompress(bytes(row["levels_gz"]))

        for ch in range(n_channels):
            ch_lo = start_hz + ch * channel_bw_hz
            ch_hi = ch_lo + channel_bw_hz

            # Bin range within this frame
            bin_lo = max(0, round((ch_lo - f0) / fstep))
            bin_hi = min(npts - 1, round((ch_hi - f0) / fstep))
            if bin_lo > bin_hi:
                continue

            for b in range(bin_lo, bin_hi + 1):
                v = _struct.unpack_from("<f", raw, b * 4)[0]
                if v > channel_max[ch]:
                    channel_max[ch] = v

    result = []
    for ch, mx in enumerate(channel_max):
        ch_lo = start_hz + ch * channel_bw_hz
        ch_hi = ch_lo + channel_bw_hz
        center = (ch_lo + ch_hi) / 2
        result.append({
            "channel_idx": ch,
            "center_hz": center,
            "start_hz":  ch_lo,
            "stop_hz":   ch_hi,
            "max_dbm": round(float(mx), 1) if mx > -999.0 else None,
        })
    return result


# ── spectrum snapshots (Phase 7: historical playback) ─────────────────────────

def list_snapshots(
    station_id: str,
    start_ms: int,
    end_ms: int,
    limit: int = 1000,
) -> list[dict]:
    """
    Return frame metadata (no blob) for the given station + time window.
    Used by the playback UI to build a timeline of available frames.
    """
    sql = """
        SELECT frame_id, station_id, period_start_ms, period_end_ms,
               sweep_count, freq_start_hz, freq_step_hz, num_points
        FROM spectrum_frames
        WHERE station_id = %s
          AND period_start_ms >= %s
          AND period_end_ms   <= %s
        ORDER BY period_start_ms
        LIMIT %s
    """
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (station_id, start_ms, end_ms, limit))
            return [dict(r) for r in cur.fetchall()]


def get_snapshot(frame_id: int) -> dict | None:
    """
    Return a single spectrum frame (with levels blob) by frame_id.
    Used by the playback UI when the user selects a specific frame.
    """
    sql = """
        SELECT frame_id, station_id, period_start_ms, period_end_ms,
               sweep_count, freq_start_hz, freq_step_hz, num_points, levels_gz
        FROM spectrum_frames
        WHERE frame_id = %s
    """
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (frame_id,))
            row = cur.fetchone()
    if row is None:
        return None
    gz_bytes = bytes(row["levels_gz"])
    return {
        "frame_id": row["frame_id"],
        "station_id": row["station_id"],
        "period_start_ms": row["period_start_ms"],
        "period_end_ms": row["period_end_ms"],
        "sweep_count": row["sweep_count"],
        "freq_start_hz": row["freq_start_hz"],
        "freq_step_hz": row["freq_step_hz"],
        "num_points": row["num_points"],
        "levels_dbm_b64": base64.b64encode(gz_bytes).decode("ascii"),
    }


# ── task expiry ───────────────────────────────────────────────────────────────

def expire_stale_tasks(timeout_minutes: int = 30) -> int:
    """
    Mark tasks that have been stuck in pending/dispatched for more than
    `timeout_minutes` as 'expired'.  Returns the number of tasks expired.
    """
    sql = """
        UPDATE tasks
        SET status = 'expired', updated_at = now()
        WHERE status IN ('pending', 'dispatched')
          AND created_at < now() - (%s * interval '1 minute')
        RETURNING task_id
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (timeout_minutes,))
            expired_ids = [r[0] for r in cur.fetchall()]
            if expired_ids:
                placeholders = ",".join(["%s"] * len(expired_ids))
                cur.execute(
                    f"""
                    UPDATE task_stations
                    SET status = 'expired'
                    WHERE task_id IN ({placeholders})
                      AND status IN ('pending', 'dispatched')
                    """,
                    expired_ids,
                )
    if expired_ids:
        log.info("Expired %d stale task(s): %s", len(expired_ids), expired_ids)
    return len(expired_ids)


# ── signal_analyses ───────────────────────────────────────────────────────────

def create_analysis(
    station_id: str,
    frame_id: int | None,
    freq_start_hz: float,
    freq_stop_hz: float,
    period_start_ms: int,
    period_end_ms: int,
    threshold_dbm: float,
    detections: list,
    ai_summary: str | None,
    ai_backend: str | None,
) -> int:
    sql = """
        INSERT INTO signal_analyses
            (station_id, frame_id, freq_start_hz, freq_stop_hz,
             period_start_ms, period_end_ms, threshold_dbm,
             detections, ai_summary, ai_backend)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING analysis_id
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (
                station_id, frame_id, freq_start_hz, freq_stop_hz,
                period_start_ms, period_end_ms, threshold_dbm,
                json.dumps(detections), ai_summary, ai_backend,
            ))
            return cur.fetchone()[0]


def list_analyses(station_id: str | None = None, limit: int = 100) -> list[dict]:
    conditions = []
    params: list = []
    if station_id:
        conditions.append("station_id = %s")
        params.append(station_id)
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    sql = f"""
        SELECT analysis_id, station_id, frame_id, freq_start_hz, freq_stop_hz,
               period_start_ms, period_end_ms, threshold_dbm,
               detections, ai_summary, ai_backend, status, created_at
        FROM signal_analyses
        {where}
        ORDER BY created_at DESC
        LIMIT %s
    """
    params.append(limit)
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]


def get_analysis(analysis_id: int) -> dict | None:
    sql = """
        SELECT analysis_id, station_id, frame_id, freq_start_hz, freq_stop_hz,
               period_start_ms, period_end_ms, threshold_dbm,
               detections, ai_summary, ai_backend, status, created_at
        FROM signal_analyses
        WHERE analysis_id = %s
    """
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (analysis_id,))
            row = cur.fetchone()
    return dict(row) if row else None


def update_analysis_status(analysis_id: int, status: str) -> bool:
    sql = "UPDATE signal_analyses SET status = %s WHERE analysis_id = %s"
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (status, analysis_id))
            return cur.rowcount > 0


# ── signal_records ────────────────────────────────────────────────────────────

def list_signal_records(status: str | None = None, limit: int = 200) -> list[dict]:
    conditions = []
    params: list = []
    if status:
        conditions.append("status = %s")
        params.append(status)
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    sql = f"""
        SELECT signal_id, name, freq_center_hz, bandwidth_hz, modulation,
               service, authority, station_id, first_seen_ms, last_seen_ms,
               max_dbm, notes, status, created_at
        FROM signal_records
        {where}
        ORDER BY freq_center_hz
        LIMIT %s
    """
    params.append(limit)
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]


def create_signal_record(
    name: str,
    freq_center_hz: float,
    bandwidth_hz: float | None,
    modulation: str | None,
    service: str | None,
    authority: str | None,
    station_id: str | None,
    first_seen_ms: int | None,
    last_seen_ms: int | None,
    max_dbm: float | None,
    notes: str | None,
) -> int:
    sql = """
        INSERT INTO signal_records
            (name, freq_center_hz, bandwidth_hz, modulation, service, authority,
             station_id, first_seen_ms, last_seen_ms, max_dbm, notes)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING signal_id
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (
                name, freq_center_hz, bandwidth_hz, modulation, service, authority,
                station_id, first_seen_ms, last_seen_ms, max_dbm, notes,
            ))
            return cur.fetchone()[0]


def update_signal_record(signal_id: int, **fields) -> bool:
    allowed = {
        "name", "freq_center_hz", "bandwidth_hz", "modulation", "service",
        "authority", "station_id", "first_seen_ms", "last_seen_ms",
        "max_dbm", "notes", "status",
    }
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return False
    set_clause = ", ".join(f"{k} = %s" for k in updates)
    sql = f"UPDATE signal_records SET {set_clause} WHERE signal_id = %s"
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (*updates.values(), signal_id))
            return cur.rowcount > 0


def delete_signal_record(signal_id: int) -> bool:
    sql = "DELETE FROM signal_records WHERE signal_id = %s"
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (signal_id,))
            return cur.rowcount > 0

"""
Task dispatch router
====================
Allows the frontend to create scan tasks, which are pushed to edge stations
via their open WebSocket connections.

Endpoints
---------
POST   /api/v1/tasks                   Create task, dispatch to stations
GET    /api/v1/tasks                   List recent tasks (summary)
GET    /api/v1/tasks/{task_id}         Full task detail + per-station results
POST   /api/v1/tasks/{task_id}/results Edge agent reports result
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid

from fastapi import APIRouter, HTTPException

from .. import db
from ..connection_manager import manager
from ..models import (
    TaskCreate, TaskListResponse, TaskOut, TaskResultIn,
    TaskStationOut, TaskSummary,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])

_VALID_TYPES = {"band_scan", "channel_scan", "if_analysis"}


def _make_task_id() -> str:
    ts = int(time.time())
    uid = uuid.uuid4().hex[:6].upper()
    return f"TASK-{ts}-{uid}"


def _row_to_summary(row: dict) -> TaskSummary:
    return TaskSummary(
        task_id=row["task_id"],
        type=row["type"],
        status=row["status"],
        created_at=str(row["created_at"]),
        station_count=int(row["station_count"]),
        completed_count=int(row["completed_count"]),
    )


def _row_to_task_out(row: dict) -> TaskOut:
    stations = []
    for s in row.get("stations", []):
        stations.append(TaskStationOut(
            station_id=s["station_id"],
            status=s["status"],
            dispatched_at=str(s["dispatched_at"]) if s.get("dispatched_at") else None,
            started_at=str(s["started_at"]) if s.get("started_at") else None,
            finished_at=str(s["finished_at"]) if s.get("finished_at") else None,
            result_b64=s.get("result_b64"),
            result_meta=s.get("result_meta"),
            error=s.get("error"),
        ))
    return TaskOut(
        task_id=row["task_id"],
        type=row["type"],
        params=row["params"],
        stream_fps=row["stream_fps"],
        status=row["status"],
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        stations=stations,
    )


# ── Create task ───────────────────────────────────────────────────────────────

@router.post("", status_code=201)
async def create_task(body: TaskCreate) -> dict:
    """
    Create a scan task and dispatch it to the target edge stations.

    If a station is not currently connected, its status is set to 'pending'
    and will remain so until the station reconnects and pulls tasks (TODO).
    """
    if body.type not in _VALID_TYPES:
        raise HTTPException(400, f"Invalid task type {body.type!r}. "
                            f"Must be one of: {sorted(_VALID_TYPES)}")
    if not body.station_ids:
        raise HTTPException(400, "station_ids must not be empty")

    task_id = _make_task_id()
    loop = asyncio.get_running_loop()

    # Persist task record
    await loop.run_in_executor(
        None, db.create_task,
        task_id, body.type, body.params, body.station_ids, body.stream_fps,
    )

    # Dispatch to connected stations
    dispatch_payload = {
        "type": "task",
        "task_id": task_id,
        "task_type": body.type,
        "params": body.params,
        "stream": {"enabled": body.stream_fps > 0, "fps": body.stream_fps},
    }

    dispatched = []
    not_connected = []
    for sid in body.station_ids:
        sent = await manager.send(sid, dispatch_payload)
        if sent:
            dispatched.append(sid)
            await loop.run_in_executor(None, db.mark_task_dispatched, task_id, sid)
        else:
            not_connected.append(sid)

    log.info(
        "Task %s (%s) created: dispatched=%s, not_connected=%s",
        task_id, body.type, dispatched, not_connected,
    )

    return {
        "task_id": task_id,
        "dispatched": dispatched,
        "not_connected": not_connected,
    }


# ── List tasks ────────────────────────────────────────────────────────────────

@router.get("", response_model=TaskListResponse)
async def list_tasks() -> TaskListResponse:
    loop = asyncio.get_running_loop()
    rows = await loop.run_in_executor(None, db.list_tasks, 200)
    summaries = [_row_to_summary(r) for r in rows]
    return TaskListResponse(tasks=summaries, total=len(summaries))


# ── Get task detail ───────────────────────────────────────────────────────────

@router.get("/{task_id}", response_model=TaskOut)
async def get_task(task_id: str) -> TaskOut:
    loop = asyncio.get_running_loop()
    row = await loop.run_in_executor(None, db.get_task, task_id)
    if row is None:
        raise HTTPException(404, f"Task {task_id!r} not found")
    return _row_to_task_out(row)


# ── Edge reports result ───────────────────────────────────────────────────────

@router.post("/{task_id}/results", status_code=204)
async def report_task_result(task_id: str, body: TaskResultIn) -> None:
    """
    Called by an edge agent when it finishes (or fails) executing a task.
    The edge posts this to the cloud; cloud stores result and updates status.
    """
    loop = asyncio.get_running_loop()
    row = await loop.run_in_executor(None, db.get_task, task_id)
    if row is None:
        raise HTTPException(404, f"Task {task_id!r} not found")

    await loop.run_in_executor(
        None, db.save_task_result,
        task_id, body.station_id, body.result_b64, body.result_meta, body.error,
    )
    log.info(
        "Task %s result from %s: %s",
        task_id, body.station_id,
        "error: " + body.error if body.error else "OK",
    )

"""
Signal Library Router
=====================
Phase 8: CRUD for catalogued/identified signals.

Endpoints
---------
GET    /api/v1/signals              List signal records
POST   /api/v1/signals              Create a new signal record
PUT    /api/v1/signals/{id}         Update an existing record
DELETE /api/v1/signals/{id}         Delete (or archive) a record
"""
from __future__ import annotations

import asyncio
import logging
from functools import partial
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from .. import db
from ..models import SignalRecordIn, SignalRecordListResponse, SignalRecordOut

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/signals", tags=["signals"])


def _row_to_out(row: dict) -> SignalRecordOut:
    return SignalRecordOut(
        signal_id=row["signal_id"],
        name=row["name"],
        freq_center_hz=row["freq_center_hz"],
        bandwidth_hz=row.get("bandwidth_hz"),
        modulation=row.get("modulation"),
        service=row.get("service"),
        authority=row.get("authority"),
        station_id=row.get("station_id"),
        first_seen_ms=row.get("first_seen_ms"),
        last_seen_ms=row.get("last_seen_ms"),
        max_dbm=row.get("max_dbm"),
        notes=row.get("notes"),
        status=row["status"],
        created_at=str(row["created_at"]),
    )


@router.get("", response_model=SignalRecordListResponse)
async def list_signals(
    status: Optional[str] = Query(None, description="Filter by status (active/archived)"),
    limit: int = Query(200, ge=1, le=1000),
) -> SignalRecordListResponse:
    loop = asyncio.get_running_loop()
    rows = await loop.run_in_executor(
        None, partial(db.list_signal_records, status, limit)
    )
    return SignalRecordListResponse(
        records=[_row_to_out(r) for r in rows],
        total=len(rows),
    )


@router.post("", status_code=201, response_model=SignalRecordOut)
async def create_signal(body: SignalRecordIn) -> SignalRecordOut:
    loop = asyncio.get_running_loop()
    signal_id = await loop.run_in_executor(
        None,
        partial(
            db.create_signal_record,
            body.name, body.freq_center_hz, body.bandwidth_hz,
            body.modulation, body.service, body.authority,
            body.station_id, body.first_seen_ms, body.last_seen_ms,
            body.max_dbm, body.notes,
        ),
    )
    rows = await loop.run_in_executor(None, partial(db.list_signal_records, None, 1000))
    row = next((r for r in rows if r["signal_id"] == signal_id), None)
    if row is None:
        raise HTTPException(500, "Failed to retrieve created record")
    return _row_to_out(row)


@router.put("/{signal_id}", response_model=SignalRecordOut)
async def update_signal(signal_id: int, body: SignalRecordIn) -> SignalRecordOut:
    loop = asyncio.get_running_loop()
    ok = await loop.run_in_executor(
        None,
        partial(
            db.update_signal_record,
            signal_id,
            name=body.name,
            freq_center_hz=body.freq_center_hz,
            bandwidth_hz=body.bandwidth_hz,
            modulation=body.modulation,
            service=body.service,
            authority=body.authority,
            station_id=body.station_id,
            first_seen_ms=body.first_seen_ms,
            last_seen_ms=body.last_seen_ms,
            max_dbm=body.max_dbm,
            notes=body.notes,
        ),
    )
    if not ok:
        raise HTTPException(404, f"Signal {signal_id} not found")
    rows = await loop.run_in_executor(None, partial(db.list_signal_records, None, 1000))
    row = next((r for r in rows if r["signal_id"] == signal_id), None)
    return _row_to_out(row)


@router.patch("/{signal_id}/archive", status_code=200)
async def archive_signal(signal_id: int) -> dict:
    loop = asyncio.get_running_loop()
    ok = await loop.run_in_executor(
        None, partial(db.update_signal_record, signal_id, status="archived")
    )
    if not ok:
        raise HTTPException(404, f"Signal {signal_id} not found")
    return {"ok": True, "signal_id": signal_id, "status": "archived"}


@router.delete("/{signal_id}", status_code=204)
async def delete_signal(signal_id: int) -> None:
    loop = asyncio.get_running_loop()
    ok = await loop.run_in_executor(
        None, partial(db.delete_signal_record, signal_id)
    )
    if not ok:
        raise HTTPException(404, f"Signal {signal_id} not found")

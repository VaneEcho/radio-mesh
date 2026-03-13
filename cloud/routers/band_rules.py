"""
Band Rules CRUD router.

GET    /api/v1/band_rules          — list all rules
POST   /api/v1/band_rules          — create a rule
PUT    /api/v1/band_rules/{id}     — update a rule
DELETE /api/v1/band_rules/{id}     — delete a rule
"""
from __future__ import annotations

import asyncio
import logging
from functools import partial

from fastapi import APIRouter, HTTPException, status

from .. import db
from ..models import BandRuleIn, BandRuleListResponse, BandRuleOut

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/band_rules", tags=["band_rules"])


@router.get("", response_model=BandRuleListResponse)
async def list_rules() -> BandRuleListResponse:
    loop = asyncio.get_running_loop()
    rules = await loop.run_in_executor(None, db.list_band_rules)
    return BandRuleListResponse(
        rules=[BandRuleOut(**r) for r in rules],
        total=len(rules),
    )


@router.post("", response_model=BandRuleOut, status_code=status.HTTP_201_CREATED)
async def create_rule(body: BandRuleIn) -> BandRuleOut:
    if body.freq_stop_hz <= body.freq_start_hz:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="freq_stop_hz must be greater than freq_start_hz",
        )
    loop = asyncio.get_running_loop()
    rule_id = await loop.run_in_executor(
        None,
        partial(
            db.create_band_rule,
            name=body.name,
            freq_start_hz=body.freq_start_hz,
            freq_stop_hz=body.freq_stop_hz,
            service=body.service,
            authority=body.authority,
            notes=body.notes,
        ),
    )
    return BandRuleOut(rule_id=rule_id, **body.model_dump())


@router.put("/{rule_id}", response_model=BandRuleOut)
async def update_rule(rule_id: int, body: BandRuleIn) -> BandRuleOut:
    loop = asyncio.get_running_loop()
    updated = await loop.run_in_executor(
        None,
        partial(db.update_band_rule, rule_id=rule_id, **body.model_dump()),
    )
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")
    return BandRuleOut(rule_id=rule_id, **body.model_dump())


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule(rule_id: int) -> None:
    loop = asyncio.get_running_loop()
    deleted = await loop.run_in_executor(
        None,
        partial(db.delete_band_rule, rule_id=rule_id),
    )
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")

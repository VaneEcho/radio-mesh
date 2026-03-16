"""
Signal Analysis Router
======================
Phase 6: Local anomaly/signal detection + optional AI analysis.

Endpoints
---------
POST   /api/v1/analysis          Run analysis on a spectrum frame or time range
GET    /api/v1/analysis          List past analyses (optionally filtered by station)
GET    /api/v1/analysis/{id}     Get a single analysis result
PATCH  /api/v1/analysis/{id}     Update status (confirmed / dismissed)
"""
from __future__ import annotations

import asyncio
import gzip
import json
import logging
import struct
from functools import partial
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from .. import db
from ..models import (
    AnalysisListResponse, AnalysisOut, AnalysisRequest,
    AnalysisStatusUpdate, SignalDetection,
)

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/analysis", tags=["analysis"])

_VALID_STATUSES = {"new", "confirmed", "dismissed"}


# ── Local signal detector ─────────────────────────────────────────────────────

def _detect_signals(
    levels_dbm: list[float],
    freq_start_hz: float,
    freq_step_hz: float,
    threshold_dbm: float,
    band_rules: list[dict],
) -> list[dict]:
    """
    Find contiguous spectral segments above `threshold_dbm`.

    For each segment compute:
      - freq_start_hz / freq_stop_hz / freq_center_hz
      - bandwidth_hz (3 dB width relative to peak)
      - peak_dbm
      - band_name from band_rules (if freq falls inside a known band)
    """
    n = len(levels_dbm)
    if n == 0:
        return []

    signals = []
    in_seg = False
    seg_start = 0

    def _make_signal(s: int, e: int) -> dict:
        seg = levels_dbm[s: e + 1]
        peak_idx_rel = max(range(len(seg)), key=lambda i: seg[i])
        peak_dbm = seg[peak_idx_rel]
        peak_hz = freq_start_hz + (s + peak_idx_rel) * freq_step_hz

        # 3 dB bandwidth around peak
        peak_idx_abs = s + peak_idx_rel
        thresh3db = peak_dbm - 3.0
        lo = peak_idx_abs
        while lo > 0 and levels_dbm[lo - 1] >= thresh3db:
            lo -= 1
        hi = peak_idx_abs
        while hi < n - 1 and levels_dbm[hi + 1] >= thresh3db:
            hi += 1

        bw_hz = (hi - lo) * freq_step_hz
        center_hz = freq_start_hz + ((lo + hi) / 2.0) * freq_step_hz

        # Band lookup
        band_name = None
        for rule in band_rules:
            if rule["freq_start_hz"] <= center_hz <= rule["freq_stop_hz"]:
                band_name = rule["name"]
                break

        return {
            "freq_start_hz": round(freq_start_hz + s * freq_step_hz, 1),
            "freq_stop_hz":  round(freq_start_hz + e * freq_step_hz, 1),
            "freq_center_hz": round(center_hz, 1),
            "bandwidth_hz": round(bw_hz, 1),
            "peak_dbm": round(float(peak_dbm), 2),
            "band_name": band_name,
        }

    for i in range(n):
        above = levels_dbm[i] > threshold_dbm
        if not in_seg and above:
            in_seg = True
            seg_start = i
        elif in_seg and not above:
            in_seg = False
            signals.append(_make_signal(seg_start, i - 1))
    if in_seg:
        signals.append(_make_signal(seg_start, n - 1))

    return signals


def _frame_to_levels(row: dict) -> tuple[list[float], float, float, int, int]:
    """Decompress a DB row's gzip blob → list of floats + metadata."""
    from base64 import b64decode
    raw_gz = b64decode(row["levels_dbm_b64"])
    raw = gzip.decompress(raw_gz)
    n = len(raw) // 4
    levels = list(struct.unpack_from(f"<{n}f", raw))
    return (
        levels,
        row["freq_start_hz"],
        row["freq_step_hz"],
        row["period_start_ms"],
        row["period_end_ms"],
    )


# ── Optional AI backend ───────────────────────────────────────────────────────

async def _ai_summarise(
    detections: list[dict],
    freq_start_hz: float,
    freq_stop_hz: float,
    backend: str,
    api_key: str | None,
) -> str | None:
    """
    Call an external AI model to interpret the detected signals.
    Returns a plain-text summary or None if unavailable.
    """
    if not detections:
        return "未在所选频段内检测到高于阈值的信号。"

    # Build a text description of the spectrum scan
    detected_lines = []
    for i, d in enumerate(detections, 1):
        detected_lines.append(
            f"  {i}. 中心频率 {d['freq_center_hz']/1e6:.3f} MHz，"
            f"带宽 {d['bandwidth_hz']/1e3:.1f} kHz，"
            f"峰值电平 {d['peak_dbm']:.1f} dBm"
            + (f"（{d['band_name']}频段）" if d.get("band_name") else "")
        )
    description = (
        f"频谱分析报告（扫描范围 {freq_start_hz/1e6:.1f}–{freq_stop_hz/1e6:.1f} MHz）：\n"
        f"共检测到 {len(detections)} 个信号：\n"
        + "\n".join(detected_lines)
    )

    prompt = (
        "你是一名无线电频谱监测专家。以下是一段频谱扫描数据：\n\n"
        + description
        + "\n\n请根据信号的频率、带宽和电平，逐条分析可能的信号类型、调制方式和归属业务，"
        "并标注是否存在异常（如非法占频、频率偏移等）。回答使用中文，简洁专业。"
    )

    try:
        if backend == "claude":
            return await _call_claude(prompt, api_key)
        elif backend == "openai":
            return await _call_openai(prompt, api_key)
        else:
            return f"[本地分析]\n{description}"
    except Exception as exc:
        log.warning("AI backend %r failed: %s", backend, exc)
        return None


async def _call_claude(prompt: str, api_key: str | None) -> str:
    import anthropic
    import asyncio

    client = anthropic.Anthropic(api_key=api_key)
    loop = asyncio.get_running_loop()

    def _sync():
        msg = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text

    return await loop.run_in_executor(None, _sync)


async def _call_openai(prompt: str, api_key: str | None) -> str:
    import openai
    import asyncio

    client = openai.AsyncOpenAI(api_key=api_key)
    resp = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1024,
    )
    return resp.choices[0].message.content


# ── Endpoints ─────────────────────────────────────────────────────────────────

def _row_to_out(row: dict) -> AnalysisOut:
    try:
        detections = json.loads(row["detections"]) if row["detections"] else []
    except Exception:
        detections = []
    return AnalysisOut(
        analysis_id=row["analysis_id"],
        station_id=row["station_id"],
        frame_id=row.get("frame_id"),
        freq_start_hz=row["freq_start_hz"],
        freq_stop_hz=row["freq_stop_hz"],
        period_start_ms=row["period_start_ms"],
        period_end_ms=row["period_end_ms"],
        threshold_dbm=row["threshold_dbm"],
        detections=[SignalDetection(**d) for d in detections],
        ai_summary=row.get("ai_summary"),
        ai_backend=row.get("ai_backend"),
        status=row["status"],
        created_at=str(row["created_at"]),
    )


@router.post("", status_code=201, response_model=AnalysisOut)
async def run_analysis(body: AnalysisRequest) -> AnalysisOut:
    """
    Run signal detection on a spectrum frame or time range.

    - If `frame_id` is given, analyse that specific frame.
    - Otherwise fetch frames from [period_start_ms, period_end_ms] and
      aggregate (take max per bin) before analysing.
    """
    loop = asyncio.get_running_loop()

    # ── Load spectrum data ──
    if body.frame_id is not None:
        frame_row = await loop.run_in_executor(
            None, partial(db.get_snapshot, body.frame_id)
        )
        if frame_row is None:
            raise HTTPException(404, f"Frame {body.frame_id} not found")
        levels, f_start, f_step, p_start, p_end = _frame_to_levels(frame_row)
        freq_start_hz = f_start
        freq_stop_hz = f_start + f_step * (len(levels) - 1)
    else:
        # Time-range: validate
        if any(v is None for v in (
            body.freq_start_hz, body.freq_stop_hz,
            body.period_start_ms, body.period_end_ms,
        )):
            raise HTTPException(
                422,
                "Provide either frame_id or (freq_start_hz, freq_stop_hz, "
                "period_start_ms, period_end_ms)",
            )
        rows = await loop.run_in_executor(
            None,
            partial(
                db.query_bundles,
                body.station_id,
                body.period_start_ms,
                body.period_end_ms,
                limit=500,
            ),
        )
        if not rows:
            raise HTTPException(404, "No spectrum frames found in the given window")

        # Aggregate: element-wise max across frames
        import numpy as np
        agg = None
        for row in rows:
            lvls, f_start, f_step, p_start, p_end = _frame_to_levels(row)
            arr = np.array(lvls, dtype=np.float32)
            if agg is None:
                agg = arr
                freq_start_hz = f_start
                freq_stop_hz = f_start + f_step * (len(lvls) - 1)
            else:
                if len(arr) == len(agg):
                    np.fmax(agg, arr, out=agg)
        levels = agg.tolist() if agg is not None else []
        p_start = rows[0]["period_start_ms"]
        p_end = rows[-1]["period_end_ms"]

    # Apply optional freq slice
    if body.freq_start_hz or body.freq_stop_hz:
        f0 = freq_start_hz
        step = (freq_stop_hz - f0) / max(len(levels) - 1, 1)
        sl_start = max(0, round((( body.freq_start_hz or f0) - f0) / step))
        sl_end = min(len(levels) - 1, round(((body.freq_stop_hz or freq_stop_hz) - f0) / step))
        levels = levels[sl_start: sl_end + 1]
        freq_start_hz = f0 + sl_start * step
        freq_stop_hz = f0 + sl_end * step

    # ── Load band rules for context ──
    band_rules = await loop.run_in_executor(None, db.list_band_rules)

    # ── Local detection ──
    detections = _detect_signals(
        levels, freq_start_hz,
        (freq_stop_hz - freq_start_hz) / max(len(levels) - 1, 1),
        body.threshold_dbm, band_rules,
    )

    # ── Optional AI analysis ──
    ai_summary = None
    ai_backend = body.ai_backend
    if ai_backend in ("claude", "openai"):
        ai_summary = await _ai_summarise(
            detections, freq_start_hz, freq_stop_hz, ai_backend, body.ai_api_key,
        )
    elif ai_backend == "local":
        ai_summary = await _ai_summarise(
            detections, freq_start_hz, freq_stop_hz, "local", None,
        )

    # ── Persist ──
    analysis_id = await loop.run_in_executor(
        None,
        partial(
            db.create_analysis,
            body.station_id,
            body.frame_id,
            freq_start_hz,
            freq_stop_hz,
            p_start,
            p_end,
            body.threshold_dbm,
            detections,
            ai_summary,
            ai_backend,
        ),
    )

    row = await loop.run_in_executor(None, partial(db.get_analysis, analysis_id))
    return _row_to_out(row)


@router.get("", response_model=AnalysisListResponse)
async def list_analyses(
    station_id: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
) -> AnalysisListResponse:
    loop = asyncio.get_running_loop()
    rows = await loop.run_in_executor(
        None, partial(db.list_analyses, station_id, limit)
    )
    return AnalysisListResponse(
        analyses=[_row_to_out(r) for r in rows],
        total=len(rows),
    )


@router.get("/{analysis_id}", response_model=AnalysisOut)
async def get_analysis(analysis_id: int) -> AnalysisOut:
    loop = asyncio.get_running_loop()
    row = await loop.run_in_executor(None, partial(db.get_analysis, analysis_id))
    if row is None:
        raise HTTPException(404, f"Analysis {analysis_id} not found")
    return _row_to_out(row)


@router.patch("/{analysis_id}", status_code=200)
async def update_analysis(analysis_id: int, body: AnalysisStatusUpdate) -> dict:
    if body.status not in _VALID_STATUSES:
        raise HTTPException(422, f"status must be one of {sorted(_VALID_STATUSES)}")
    loop = asyncio.get_running_loop()
    ok = await loop.run_in_executor(
        None, partial(db.update_analysis_status, analysis_id, body.status)
    )
    if not ok:
        raise HTTPException(404, f"Analysis {analysis_id} not found")
    return {"ok": True, "analysis_id": analysis_id, "status": body.status}

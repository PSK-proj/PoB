from __future__ import annotations

import asyncio
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from lb.clients.clientgen_api import post as clientgen_post
from lb.clients.worker_api import reset_metrics as worker_reset_metrics


router = APIRouter(prefix="/experiment", tags=["experiment"])


class ResetResult(BaseModel):
    target: str
    id: Optional[str] = None
    ok: bool
    detail: Optional[str] = None


class ExperimentResetResponse(BaseModel):
    ok: bool
    results: list[ResetResult]


async def _reset_workers(rt) -> list[ResetResult]:
    async def one(w):
        try:
            await worker_reset_metrics(rt.http, w)
            return ResetResult(target="worker", id=w.id, ok=True)
        except Exception as e:
            return ResetResult(target="worker", id=w.id, ok=False, detail=str(e))

    res = await asyncio.gather(*[one(w) for w in rt.workers], return_exceptions=False)
    return list(res)


@router.post("/reset", response_model=ExperimentResetResponse)
async def reset_experiment(request: Request):
    rt = request.app.state.rt

    results: list[ResetResult] = []

    try:
        await clientgen_post("/stop", None)
        results.append(ResetResult(target="clientgen", id="stop", ok=True))
    except (httpx.HTTPError, Exception) as e:
        results.append(ResetResult(target="clientgen", id="stop", ok=False, detail=str(e)))

    try:
        await clientgen_post("/reset", None)
        results.append(ResetResult(target="clientgen", id="reset", ok=True))
    except (httpx.HTTPError, Exception) as e:
        results.append(ResetResult(target="clientgen", id="reset", ok=False, detail=str(e)))

    results.extend(await _reset_workers(rt))

    try:
        async with rt.balancer.lock:
            for w in rt.workers:
                w.assigned = 0
                w.ok = 0
                w.fail = 0
                w.avg_latency_ms = 0.0
                w.current_weight = 0
                w.disabled_until = 0.0
                if w.online:
                    w.last_error = None

        results.append(ResetResult(target="lb", id="runtime_stats", ok=True))
    except Exception as e:
        results.append(ResetResult(target="lb", id="runtime_stats", ok=False, detail=str(e)))

    try:
        async with rt.history_lock:
            rt.history.clear()
        results.append(ResetResult(target="lb", id="history", ok=True))
    except Exception as e:
        results.append(ResetResult(target="lb", id="history", ok=False, detail=str(e)))

    ok = all(r.ok for r in results)
    return ExperimentResetResponse(ok=ok, results=results)

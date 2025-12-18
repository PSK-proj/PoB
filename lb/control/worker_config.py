from __future__ import annotations

from typing import Any, Optional

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from lb.clients.worker_api import get_config as api_get_config
from lb.clients.worker_api import patch_config as api_patch_config
from lb.clients.worker_api import fetch_metrics as api_fetch_metrics
from lb.clients.worker_api import reset_metrics as api_reset_metrics


router = APIRouter(tags=["workers"])


class ErrorResponse(BaseModel):
    code: str
    message: str
    worker_id: str
    op: str


class WorkerConfig(BaseModel):
    base_lat_ms: int
    jitter_ms: int
    capacity: int
    weight: int


class WorkerMetrics(BaseModel):
    worker_id: str
    inflight: int
    total: int
    ok: int
    fail: int
    last_error: Optional[str] = None
    last_simulated_ms: Optional[int] = None
    last_completed_at: Optional[float] = None


class MetricsResetResponse(BaseModel):
    before: WorkerMetrics
    after: WorkerMetrics


class WorkerConfigPatch(BaseModel):
    base_lat_ms: int | None = Field(default=None, ge=0, le=60_000)
    jitter_ms: int | None = Field(default=None, ge=0, le=60_000)
    capacity: int | None = Field(default=None, ge=1, le=100_000)
    weight: int | None = Field(default=None, ge=1, le=1000)


def _find_worker(rt: Any, worker_id: str):
    for w in rt.workers:
        host = w.url.replace("http://", "").replace("https://", "").split(":")[0]
        if w.id == worker_id or host == worker_id:
            return w
    return None


def _upstream_error(worker_id: str, op: str, e: Exception) -> HTTPException:
    return HTTPException(
        status_code=502,
        detail={
            "code": "upstream_error",
            "message": str(e),
            "worker_id": worker_id,
            "op": op,
        },
    )


_RESPONSES = {
    404: {"description": "Worker not found"},
    400: {"description": "Bad request"},
    502: {"model": ErrorResponse, "description": "Upstream worker error"},
}


@router.get("/workers/{worker_id}/config", response_model=WorkerConfig, responses=_RESPONSES)
async def get_worker_config(request: Request, worker_id: str):
    rt = request.app.state.rt
    w = _find_worker(rt, worker_id)
    if w is None:
        raise HTTPException(status_code=404, detail="worker not found")

    try:
        data = await api_get_config(rt.http, w)
        return WorkerConfig(**data)
    except (httpx.HTTPError, ValueError, TypeError) as e:
        raise _upstream_error(worker_id=worker_id, op="get_config", e=e)


@router.patch("/workers/{worker_id}/config", response_model=WorkerConfig, responses=_RESPONSES)
async def patch_worker_config(request: Request, worker_id: str, payload: WorkerConfigPatch):
    rt = request.app.state.rt
    w = _find_worker(rt, worker_id)
    if w is None:
        raise HTTPException(status_code=404, detail="worker not found")

    patch = payload.model_dump(exclude_none=True)
    if not patch:
        raise HTTPException(status_code=400, detail="empty patch")

    try:
        resp = await api_patch_config(rt.http, w, patch)
        cfg = WorkerConfig(**resp)

        async with rt.balancer.lock:
            w.reported_weight = max(1, int(cfg.weight))
            w.reported_base_lat_ms = int(cfg.base_lat_ms)
            w.last_error = None
            w.recompute_effective(rt.weight_mode)

        return cfg

    except (httpx.HTTPError, ValueError, TypeError) as e:
        raise _upstream_error(worker_id=worker_id, op="patch_config", e=e)


@router.get("/workers/{worker_id}/metrics", response_model=WorkerMetrics, responses=_RESPONSES)
async def get_worker_metrics(request: Request, worker_id: str):
    rt = request.app.state.rt
    w = _find_worker(rt, worker_id)
    if w is None:
        raise HTTPException(status_code=404, detail="worker not found")

    try:
        data = await api_fetch_metrics(rt.http, w)
        return WorkerMetrics(**data)
    except (httpx.HTTPError, ValueError, TypeError) as e:
        raise _upstream_error(worker_id=worker_id, op="get_metrics", e=e)


@router.post("/workers/{worker_id}/metrics/reset", response_model=MetricsResetResponse, responses=_RESPONSES)
async def reset_worker_metrics(request: Request, worker_id: str):
    rt = request.app.state.rt
    w = _find_worker(rt, worker_id)
    if w is None:
        raise HTTPException(status_code=404, detail="worker not found")

    try:
        data = await api_reset_metrics(rt.http, w)
        return MetricsResetResponse(**data)
    except (httpx.HTTPError, ValueError, TypeError) as e:
        raise _upstream_error(worker_id=worker_id, op="reset_metrics", e=e)

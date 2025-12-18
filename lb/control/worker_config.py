from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from lb.clients.worker_api import get_config as api_get_config
from lb.clients.worker_api import patch_config as api_patch_config
from lb.clients.worker_api import fetch_metrics as api_fetch_metrics
from lb.clients.worker_api import reset_metrics as api_reset_metrics


router = APIRouter(tags=["workers"])


class WorkerConfigPatch(BaseModel):
    base_lat_ms: int | None = Field(default=None, ge=0, le=60_000)
    jitter_ms: int | None = Field(default=None, ge=0, le=60_000)
    capacity: int | None = Field(default=None, ge=1, le=100_000)
    weight: int | None = Field(default=None, ge=1, le=1000)


def _find_worker(rt, worker_id: str):
    for w in rt.workers:
        host = w.url.replace("http://", "").replace("https://", "").split(":")[0]
        if w.id == worker_id or host == worker_id:
            return w
    return None


@router.get("/workers/{worker_id}/config")
async def get_worker_config(request: Request, worker_id: str):
    rt = request.app.state.rt
    w = _find_worker(rt, worker_id)
    if w is None:
        raise HTTPException(status_code=404, detail="worker not found")
    try:
        return await api_get_config(rt.http, w)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"worker error: {e}")


@router.patch("/workers/{worker_id}/config")
async def patch_worker_config(request: Request, worker_id: str, payload: WorkerConfigPatch):
    rt = request.app.state.rt
    w = _find_worker(rt, worker_id)
    if w is None:
        raise HTTPException(status_code=404, detail="worker not found")

    data = payload.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="empty patch")

    try:
        resp = await api_patch_config(rt.http, w, data)

        async with rt.balancer.lock:
            if isinstance(resp, dict):
                if "weight" in resp:
                    try:
                        w.reported_weight = max(1, int(resp["weight"]))
                    except Exception:
                        pass

                if "base_lat_ms" in resp:
                    try:
                        w.reported_base_lat_ms = int(resp["base_lat_ms"])
                    except Exception:
                        pass

                w.last_error = None

            w.recompute_effective(rt.weight_mode)

        return resp

    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"worker error: {e}")


@router.get("/workers/{worker_id}/metrics")
async def get_worker_metrics(request: Request, worker_id: str):
    rt = request.app.state.rt
    w = _find_worker(rt, worker_id)
    if w is None:
        raise HTTPException(status_code=404, detail="worker not found")
    try:
        return await api_fetch_metrics(rt.http, w)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"worker error: {e}")


@router.post("/workers/{worker_id}/metrics/reset")
async def reset_worker_metrics(request: Request, worker_id: str):
    rt = request.app.state.rt
    w = _find_worker(rt, worker_id)
    if w is None:
        raise HTTPException(status_code=404, detail="worker not found")
    try:
        return await api_reset_metrics(rt.http, w)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"worker error: {e}")

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter(tags=["weights"])


class WeightModeRequest(BaseModel):
    mode: str = Field(pattern="^(manual|auto)$")


class ManualWeightRequest(BaseModel):
    weight: int = Field(ge=1, le=1000)


def _find_worker(rt, worker_id: str):
    for w in rt.workers:
        host = w.url.replace("http://", "").replace("https://", "").split(":")[0]
        if w.id == worker_id or host == worker_id:
            return w
    return None


@router.post("/lb/weight-mode")
async def set_weight_mode(request: Request, payload: WeightModeRequest):
    rt = request.app.state.rt
    async with rt.balancer.lock:
        rt.weight_mode = payload.mode
        for w in rt.workers:
            w.recompute_effective(rt.weight_mode)
    return {"ok": True, "mode": rt.weight_mode}


@router.get("/lb/weight-mode")
async def get_weight_mode(request: Request):
    rt = request.app.state.rt
    return {"mode": rt.weight_mode}


@router.patch("/workers/{worker_id}/manual-weight")
async def set_manual_weight(request: Request, worker_id: str, payload: ManualWeightRequest):
    rt = request.app.state.rt
    w = _find_worker(rt, worker_id)
    if w is None:
        raise HTTPException(status_code=404, detail="worker not found")
    if rt.weight_mode != "manual":
        raise HTTPException(status_code=409, detail="manual_weight can be set only in manual mode")

    async with rt.balancer.lock:
        w.manual_weight = int(payload.weight)
        w.recompute_effective(rt.weight_mode)

    return {"ok": True, "worker_id": w.id, "manual_weight": w.manual_weight, "effective_weight": w.effective_weight}


@router.delete("/workers/{worker_id}/manual-weight")
async def clear_manual_weight(request: Request, worker_id: str):
    rt = request.app.state.rt
    w = _find_worker(rt, worker_id)
    if w is None:
        raise HTTPException(status_code=404, detail="worker not found")

    async with rt.balancer.lock:
        w.manual_weight = None
        w.recompute_effective(rt.weight_mode)

    return {"ok": True, "worker_id": w.id, "manual_weight": w.manual_weight, "effective_weight": w.effective_weight}

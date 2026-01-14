from __future__ import annotations

from typing import Optional, Any

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel


router = APIRouter(tags=["faults"])


class ErrorResponse(BaseModel):
    code: str
    message: str
    worker_id: str
    op: str


class FaultView(BaseModel):
    id: str
    kind: str
    created_at: float
    expires_at: Optional[float] = None
    spec: dict


def _find_worker(rt, worker_id: str):
    for w in rt.workers:
        host = w.url.replace("http://", "").replace("https://", "").split(":")[0]
        if w.id == worker_id or host == worker_id:
            return w
    return None


def _upstream_error(worker_id: str, op: str, e: Exception) -> HTTPException:
    return HTTPException(
        status_code=502,
        detail={"code": "upstream_error", "message": str(e), "worker_id": worker_id, "op": op},
    )


_RESPONSES = {
    404: {"description": "Worker not found"},
    502: {"model": ErrorResponse, "description": "Upstream worker error"},
}


@router.get("/workers/{worker_id}/faults", response_model=list[FaultView], responses=_RESPONSES)
async def list_worker_faults(request: Request, worker_id: str):
    rt = request.app.state.rt
    w = _find_worker(rt, worker_id)
    if w is None:
        raise HTTPException(status_code=404, detail="worker not found")
    try:
        r = await rt.http.get(f"{w.url}/faults")
        r.raise_for_status()
        return r.json()
    except Exception as e:
        raise _upstream_error(worker_id, "list_faults", e)


@router.post("/workers/{worker_id}/faults", response_model=FaultView, responses=_RESPONSES)
async def add_worker_fault(request: Request, worker_id: str, payload: dict):
    rt = request.app.state.rt
    w = _find_worker(rt, worker_id)
    if w is None:
        raise HTTPException(status_code=404, detail="worker not found")
    try:
        r = await rt.http.post(f"{w.url}/faults", json=payload)
        r.raise_for_status()
        return r.json()
    except httpx.HTTPError as e:
        raise _upstream_error(worker_id, "add_fault", e)


@router.delete("/workers/{worker_id}/faults/{fault_id}", responses=_RESPONSES)
async def delete_worker_fault(request: Request, worker_id: str, fault_id: str):
    rt = request.app.state.rt
    w = _find_worker(rt, worker_id)
    if w is None:
        raise HTTPException(status_code=404, detail="worker not found")
    try:
        r = await rt.http.delete(f"{w.url}/faults/{fault_id}")
        r.raise_for_status()
        return r.json()
    except httpx.HTTPError as e:
        raise _upstream_error(worker_id, "delete_fault", e)


@router.delete("/workers/{worker_id}/faults", responses=_RESPONSES)
async def clear_worker_faults(request: Request, worker_id: str):
    rt = request.app.state.rt
    w = _find_worker(rt, worker_id)
    if w is None:
        raise HTTPException(status_code=404, detail="worker not found")
    try:
        r = await rt.http.delete(f"{w.url}/faults")
        r.raise_for_status()
        return r.json()
    except httpx.HTTPError as e:
        raise _upstream_error(worker_id, "clear_faults", e)

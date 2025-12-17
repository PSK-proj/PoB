from __future__ import annotations

import os
import time
import asyncio
from dataclasses import dataclass
from typing import Any, Optional
from contextlib import asynccontextmanager, suppress

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from lb.control.traffic import router as traffic_router
from lb.core.registry import WorkerState
from lb.core.smooth_wrr import SmoothWRR
from lb.clients.worker_api import fetch_health, forward_handle


WORKER_URLS = os.getenv("WORKER_URLS", "").strip()
REQUEST_TIMEOUT_SEC = float(os.getenv("LB_REQUEST_TIMEOUT_SEC", "2.0"))
HEALTH_INTERVAL_SEC = float(os.getenv("LB_HEALTH_INTERVAL_SEC", "2.0"))
DISABLE_ON_FAIL_SEC = float(os.getenv("LB_DISABLE_ON_FAIL_SEC", "3.0"))
RETRY_ATTEMPTS = int(os.getenv("LB_RETRY_ATTEMPTS", "2"))
LAT_EWMA_ALPHA = float(os.getenv("LB_LAT_EWMA_ALPHA", "0.2"))


class LBRequest(BaseModel):
    payload: dict = Field(default_factory=dict)


class WorkerView(BaseModel):
    id: str
    url: str
    weight: int
    online: bool
    assigned: int
    assigned_pct: float
    ok: int
    fail: int
    avg_latency_ms: float
    last_error: str | None
    last_seen: float | None


class LBResponse(BaseModel):
    chosen_worker: str
    attempt: int
    worker_status: int
    lb_forward_ms: float
    worker_body: Any

@dataclass
class Runtime:
    workers: list[WorkerState]
    balancer: SmoothWRR
    http: httpx.AsyncClient
    health_task: Optional[asyncio.Task] = None


def _parse_worker_urls(raw: str) -> list[str]:
    return [x.strip() for x in raw.split(",") if x.strip()]


def _assigned_pct(assigned: int, total: int) -> float:
    return (assigned / total) * 100.0 if total > 0 else 0.0


def _ewma(prev: float, new: float, alpha: float) -> float:
    return new if prev <= 0 else (alpha * new) + ((1 - alpha) * prev)


def _disable_temporarily(w: WorkerState, seconds: float) -> None:
    w.disabled_until = time.time() + seconds


def _record_success(w: WorkerState, latency_ms: float) -> None:
    w.ok += 1
    w.avg_latency_ms = _ewma(w.avg_latency_ms, latency_ms, LAT_EWMA_ALPHA)
    w.last_error = None


def _record_failure(w: WorkerState, err: str) -> None:
    w.fail += 1
    w.last_error = err


async def _refresh_health_once(rt: Runtime) -> None:
    async def _probe(w: WorkerState):
        try:
            data = await fetch_health(rt.http, w)
            return w, data, None
        except Exception as e:
            return w, None, e

    results = await asyncio.gather(*[_probe(w) for w in rt.workers], return_exceptions=False)

    now = time.time()
    for w, data, err in results:
        if err is not None:
            w.online = False
            w.last_error = f"health: {err}"
            continue

        w.online = True
        w.last_seen = now
        w.last_error = None

        if isinstance(data, dict):
            if "worker_id" in data:
                w.id = str(data["worker_id"])
            if "weight" in data:
                try:
                    w.weight = int(data["weight"])
                except Exception:
                    pass


async def _health_loop(rt: Runtime) -> None:
    while True:
        await asyncio.sleep(HEALTH_INTERVAL_SEC)
        try:
            await _refresh_health_once(rt)
        except Exception:
            pass


async def _forward_with_metrics(rt: Runtime, w: WorkerState, payload: dict) -> tuple[int, Any, float]:
    status, body, ms = await forward_handle(
        rt.http,
        w,
        payload=payload,
        timeout_sec=REQUEST_TIMEOUT_SEC,
    )
    if 200 <= status < 300:
        _record_success(w, ms)
    else:
        _record_failure(w, f"http {status}")
        if status >= 500:
            _disable_temporarily(w, DISABLE_ON_FAIL_SEC)
    return status, body, ms


async def _attempt_once(rt: Runtime, payload: dict) -> tuple[Optional[LBResponse], Optional[str], bool]:
    """
    Returns: (response_or_none, last_error_or_none, should_retry)
    """
    w = await rt.balancer.choose()
    if w is None:
        return None, "No eligible workers", False

    try:
        status, body, ms = await _forward_with_metrics(rt, w, payload)
        resp = LBResponse(
            chosen_worker=w.id,
            attempt=0,
            worker_status=status,
            lb_forward_ms=round(ms, 3),
            worker_body=body,
        )

        should_retry = status >= 500
        return resp, w.last_error, should_retry

    except Exception as e:
        _record_failure(w, f"forward: {e}")
        _disable_temporarily(w, DISABLE_ON_FAIL_SEC)
        return None, w.last_error, True


@asynccontextmanager
async def lifespan(app: FastAPI):
    urls = _parse_worker_urls(WORKER_URLS)
    if not urls:
        raise RuntimeError("WORKER_URLS is empty")

    http = httpx.AsyncClient(timeout=5.0)

    workers: list[WorkerState] = []
    for u in urls:
        host = u.replace("http://", "").replace("https://", "").split(":")[0]
        workers.append(WorkerState(id=host, url=u, weight=1))

    rt = Runtime(
        workers=workers,
        balancer=SmoothWRR(workers),
        http=http,
        health_task=None,
    )

    await _refresh_health_once(rt)
    rt.health_task = asyncio.create_task(_health_loop(rt))

    app.state.rt = rt
    try:
        yield
    finally:
        if rt.health_task is not None:
            rt.health_task.cancel()
            with suppress(asyncio.CancelledError):
                await rt.health_task
        await rt.http.aclose()


app = FastAPI(title="Load Balancer", version="0.2.0", lifespan=lifespan)
app.include_router(traffic_router)



@app.get("/health")
def health():
    return {"status": "ok", "service": "lb"}


@app.get("/workers", response_model=list[WorkerView])
def list_workers():
    rt: Runtime = app.state.rt
    total = sum(w.assigned for w in rt.workers)

    return [
        WorkerView(
            id=w.id,
            url=w.url,
            weight=w.weight,
            online=w.online,
            assigned=w.assigned,
            assigned_pct=round(_assigned_pct(w.assigned, total), 3),
            ok=w.ok,
            fail=w.fail,
            avg_latency_ms=round(w.avg_latency_ms, 3),
            last_error=w.last_error,
            last_seen=w.last_seen if w.last_seen > 0 else None,
        )
        for w in rt.workers
    ]


@app.post("/request", response_model=LBResponse)
async def handle_request(req: LBRequest):
    rt: Runtime = app.state.rt

    last_err: Optional[str] = None

    for attempt in range(1, max(1, RETRY_ATTEMPTS) + 1):
        resp, err, should_retry = await _attempt_once(rt, req.payload)
        if resp is not None:
            resp.attempt = attempt
            if should_retry and attempt < RETRY_ATTEMPTS:
                last_err = err
                continue
            return resp

        last_err = err
        if not should_retry:
            break

    raise HTTPException(status_code=502, detail=f"All attempts failed: {last_err}")

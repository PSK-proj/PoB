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
from lb.control.weights import router as weights_router
from lb.core.registry import WorkerState
from lb.core.smooth_wrr import SmoothWRR
from lb.clients.worker_api import fetch_health, forward_handle
from lb.stream.state_stream import router as stream_router
from lb.control.worker_config import router as worker_config_router
from lb.control.worker_faults import router as worker_faults_router
from lb.control.experiment import router as experiment_router


WORKER_URLS = os.getenv("WORKER_URLS", "").strip()

REQUEST_TIMEOUT_SEC = float(os.getenv("LB_REQUEST_TIMEOUT_SEC", "2.0"))
HEALTH_INTERVAL_SEC = float(os.getenv("LB_HEALTH_INTERVAL_SEC", "2.0"))
DISABLE_ON_FAIL_SEC = float(os.getenv("LB_DISABLE_ON_FAIL_SEC", "3.0"))
RETRY_ATTEMPTS = int(os.getenv("LB_RETRY_ATTEMPTS", "2"))
LAT_EWMA_ALPHA = float(os.getenv("LB_LAT_EWMA_ALPHA", "0.2"))
LB_STREAM_INTERVAL_SEC = float(os.getenv("LB_STREAM_INTERVAL_SEC", "0.5"))

LB_WEIGHT_MODE = os.getenv("LB_WEIGHT_MODE", "manual").strip().lower()
AUTO_WEIGHT_INTERVAL_SEC = float(os.getenv("AUTO_WEIGHT_INTERVAL_SEC", "2.0"))
AUTO_WEIGHT_MAX = int(os.getenv("AUTO_WEIGHT_MAX", "10"))


class LBRequest(BaseModel):
    payload: dict = Field(default_factory=dict)


class WorkerView(BaseModel):
    id: str
    url: str
    online: bool

    reported_weight: int
    manual_weight: int | None
    auto_weight: int | None
    effective_weight: int

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


class LBState(BaseModel):
    weight_mode: str
    total_assigned: int
    total_ok: int
    total_fail: int
    workers: list[WorkerView]


@dataclass
class Runtime:
    workers: list[WorkerState]
    balancer: SmoothWRR
    http: httpx.AsyncClient
    weight_mode: str = "manual"
    health_task: Optional[asyncio.Task] = None
    auto_task: Optional[asyncio.Task] = None


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

    async with rt.balancer.lock:
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
                        w.reported_weight = max(1, int(data["weight"]))
                    except Exception:
                        pass
                if "base_lat_ms" in data:
                    try:
                        w.reported_base_lat_ms = int(data["base_lat_ms"])
                    except Exception:
                        pass

            w.recompute_effective(rt.weight_mode)


async def _health_loop(rt: Runtime) -> None:
    while True:
        await asyncio.sleep(HEALTH_INTERVAL_SEC)
        try:
            await _refresh_health_once(rt)
        except Exception:
            pass


def _compute_auto_weights(rt: Runtime) -> None:
    scores: list[tuple[WorkerState, float]] = []
    for w in rt.workers:
        if not w.online:
            continue

        total = max(1, w.ok + w.fail)
        fail_rate = w.fail / total

        lat = w.avg_latency_ms
        if lat <= 0 and w.reported_base_lat_ms is not None:
            lat = float(w.reported_base_lat_ms)
        if lat <= 0:
            lat = 50.0

        score = (1.0 / (lat + 1.0)) * (1.0 - fail_rate)
        scores.append((w, max(0.0, score)))

    if not scores:
        return

    max_score = max(s for _, s in scores) or 1.0

    for w, s in scores:
        w.auto_weight = max(1, int(round(AUTO_WEIGHT_MAX * (s / max_score))))


async def _auto_loop(rt: Runtime) -> None:
    while True:
        await asyncio.sleep(AUTO_WEIGHT_INTERVAL_SEC)

        if rt.weight_mode != "auto":
            continue

        async with rt.balancer.lock:
            _compute_auto_weights(rt)
            for w in rt.workers:
                w.recompute_effective(rt.weight_mode)


def _build_worker_views(rt: Runtime) -> list[WorkerView]:
    total = sum(w.assigned for w in rt.workers)
    return [
        WorkerView(
            id=w.id,
            url=w.url,
            online=w.online,
            reported_weight=w.reported_weight,
            manual_weight=w.manual_weight,
            auto_weight=w.auto_weight,
            effective_weight=w.effective_weight,
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    urls = _parse_worker_urls(WORKER_URLS)
    if not urls:
        raise RuntimeError("WORKER_URLS is empty")

    if LB_WEIGHT_MODE not in {"manual", "auto"}:
        raise RuntimeError("LB_WEIGHT_MODE must be 'manual' or 'auto'")

    http = httpx.AsyncClient(timeout=5.0)

    workers: list[WorkerState] = []
    for u in urls:
        host = u.replace("http://", "").replace("https://", "").split(":")[0]
        ws = WorkerState(id=host, url=u)
        ws.recompute_effective(LB_WEIGHT_MODE)
        workers.append(ws)

    rt = Runtime(
        workers=workers,
        balancer=SmoothWRR(workers),
        http=http,
        weight_mode=LB_WEIGHT_MODE,
    )

    await _refresh_health_once(rt)
    rt.health_task = asyncio.create_task(_health_loop(rt))
    rt.auto_task = asyncio.create_task(_auto_loop(rt))

    app.state.rt = rt
    app.state.stream_interval_sec = max(0.05, LB_STREAM_INTERVAL_SEC)
    try:
        yield
    finally:
        for task in (rt.health_task, rt.auto_task):
            if task is not None:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
        await rt.http.aclose()


app = FastAPI(title="Load Balancer", version="0.3.0", lifespan=lifespan)
app.include_router(traffic_router)
app.include_router(weights_router)
app.include_router(stream_router)
app.include_router(worker_config_router)
app.include_router(worker_faults_router)
app.include_router(experiment_router)


@app.get("/health")
def health():
    return {"status": "ok", "service": "lb"}


@app.get("/workers", response_model=list[WorkerView])
def list_workers():
    rt: Runtime = app.state.rt
    return _build_worker_views(rt)


@app.get("/state", response_model=LBState)
def state():
    rt: Runtime = app.state.rt
    total_assigned = sum(w.assigned for w in rt.workers)
    total_ok = sum(w.ok for w in rt.workers)
    total_fail = sum(w.fail for w in rt.workers)
    return LBState(
        weight_mode=rt.weight_mode,
        total_assigned=total_assigned,
        total_ok=total_ok,
        total_fail=total_fail,
        workers=_build_worker_views(rt),
    )


@app.post("/request", response_model=LBResponse)
async def handle_request(req: LBRequest):
    rt: Runtime = app.state.rt
    last_err: Optional[str] = None

    for attempt in range(1, max(1, RETRY_ATTEMPTS) + 1):
        w = await rt.balancer.choose()
        if w is None:
            raise HTTPException(status_code=503, detail="No eligible workers")

        try:
            status, body, ms = await forward_handle(
                rt.http, w, payload=req.payload, timeout_sec=REQUEST_TIMEOUT_SEC
            )

            if 200 <= status < 300:
                _record_success(w, ms)
                return LBResponse(
                    chosen_worker=w.id,
                    attempt=attempt,
                    worker_status=status,
                    lb_forward_ms=round(ms, 3),
                    worker_body=body,
                )

            _record_failure(w, f"http {status}")
            last_err = w.last_error

            if status >= 500:
                _disable_temporarily(w, DISABLE_ON_FAIL_SEC)
                continue

            return LBResponse(
                chosen_worker=w.id,
                attempt=attempt,
                worker_status=status,
                lb_forward_ms=round(ms, 3),
                worker_body=body,
            )

        except Exception as e:
            _record_failure(w, f"forward: {e}")
            last_err = w.last_error
            _disable_temporarily(w, DISABLE_ON_FAIL_SEC)
            continue

    raise HTTPException(status_code=502, detail=f"All attempts failed: {last_err}")

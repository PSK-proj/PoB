from __future__ import annotations

import os
import time
import asyncio
import random
from dataclasses import dataclass, field
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse, JSONResponse
from pydantic import BaseModel, Field

from worker.faults import FaultCreate, FaultRegistry, FaultView, should_trigger


app = FastAPI(title="Worker", version="0.5.0")

WORKER_ID = os.getenv("WORKER_ID", "worker-unknown")


class WorkerConfig(BaseModel):
    base_lat_ms: int = Field(default=20, ge=0, le=60_000)
    jitter_ms: int = Field(default=5, ge=0, le=60_000)
    capacity: int = Field(default=50, ge=1, le=100_000)
    weight: int = Field(default=1, ge=1, le=1000)


class WorkerConfigPatch(BaseModel):
    base_lat_ms: int | None = Field(default=None, ge=0, le=60_000)
    jitter_ms: int | None = Field(default=None, ge=0, le=60_000)
    capacity: int | None = Field(default=None, ge=1, le=100_000)
    weight: int | None = Field(default=None, ge=1, le=1000)


class Metrics(BaseModel):
    worker_id: str
    inflight: int
    total: int
    ok: int
    fail: int
    last_error: str | None
    last_simulated_ms: int | None
    last_completed_at: float | None


class MetricsResetResponse(BaseModel):
    before: Metrics
    after: Metrics


class WorkRequest(BaseModel):
    payload: dict | None = None


class WorkResponse(BaseModel):
    worker_id: str
    message: str
    simulated_ms: int


@dataclass
class Runtime:
    cfg: WorkerConfig
    inflight: int = 0
    total: int = 0
    ok: int = 0
    fail: int = 0
    last_error: Optional[str] = None
    last_simulated_ms: Optional[int] = None
    last_completed_at: Optional[float] = None

    faults: FaultRegistry = field(default_factory=FaultRegistry)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


def _cfg_from_env() -> WorkerConfig:
    return WorkerConfig(
        base_lat_ms=int(os.getenv("BASE_LAT_MS", "20")),
        jitter_ms=int(os.getenv("JITTER_MS", "5")),
        capacity=int(os.getenv("CAPACITY", "50")),
        weight=int(os.getenv("WEIGHT", "1")),
    )


RT = Runtime(cfg=_cfg_from_env())


async def _snapshot_metrics() -> Metrics:
    async with RT.lock:
        return Metrics(
            worker_id=WORKER_ID,
            inflight=RT.inflight,
            total=RT.total,
            ok=RT.ok,
            fail=RT.fail,
            last_error=RT.last_error,
            last_simulated_ms=RT.last_simulated_ms,
            last_completed_at=RT.last_completed_at,
        )


def _sum_delay_ms(active_faults) -> int:
    total = 0
    for f in active_faults:
        if f.kind != "delay":
            continue
        prob = float(f.spec.get("probability", 1.0))
        if should_trigger(prob):
            total += int(f.spec.get("delay_ms", 0))
    return max(0, total)


def _sum_cpu_burn_ms(active_faults) -> int:
    total = 0
    for f in active_faults:
        if f.kind != "cpu_burn":
            continue
        prob = float(f.spec.get("probability", 1.0))
        if should_trigger(prob):
            total += int(f.spec.get("burn_ms", 0))
    return max(0, total)


def _busy_cpu(burn_ms: int) -> None:
    end = time.perf_counter() + (burn_ms / 1000.0)
    x = 0
    while time.perf_counter() < end:
        x ^= 1


def _pick_drop(active_faults):
    for f in active_faults:
        if f.kind != "drop":
            continue
        prob = float(f.spec.get("probability", 1.0))
        if should_trigger(prob):
            return f
    return None


def _pick_corrupt(active_faults):
    for f in active_faults:
        if f.kind != "corrupt":
            continue
        prob = float(f.spec.get("probability", 1.0))
        if should_trigger(prob):
            return f
    return None


def _pick_error(active_faults):
    for f in active_faults:
        if f.kind != "error":
            continue
        prob = float(f.spec.get("probability", 1.0))
        if should_trigger(prob):
            return f
    return None


@app.get("/health")
async def health():
    async with RT.lock:
        cfg = RT.cfg.model_dump()
    return {"status": "ok", "worker_id": WORKER_ID, **cfg}


@app.get("/config", response_model=WorkerConfig)
async def get_config():
    async with RT.lock:
        return RT.cfg


@app.patch("/config", response_model=WorkerConfig)
async def patch_config(patch: WorkerConfigPatch):
    data = patch.model_dump(exclude_none=True)
    async with RT.lock:
        RT.cfg = RT.cfg.model_copy(update=data)
        return RT.cfg


@app.get("/metrics", response_model=Metrics)
async def metrics():
    return await _snapshot_metrics()


@app.post("/metrics/reset", response_model=MetricsResetResponse)
async def reset_metrics():
    before = await _snapshot_metrics()
    async with RT.lock:
        RT.total = 0
        RT.ok = 0
        RT.fail = 0
        RT.last_error = None
        RT.last_simulated_ms = None
        RT.last_completed_at = None
    after = await _snapshot_metrics()
    return MetricsResetResponse(before=before, after=after)


@app.get("/faults", response_model=list[FaultView])
async def list_faults():
    async with RT.lock:
        return RT.faults.list_views()


@app.post("/faults", response_model=FaultView)
async def add_fault(payload: FaultCreate):
    async with RT.lock:
        return RT.faults.add(payload)


@app.delete("/faults/{fault_id}")
async def delete_fault(fault_id: str):
    async with RT.lock:
        ok = RT.faults.delete(fault_id)
    if not ok:
        raise HTTPException(status_code=404, detail="fault not found")
    return {"ok": True, "fault_id": fault_id}


@app.delete("/faults")
async def clear_faults():
    async with RT.lock:
        n = RT.faults.clear()
    return {"ok": True, "cleared": n}


@app.post("/handle", response_model=WorkResponse)
async def handle(req: WorkRequest):
    async with RT.lock:
        RT.total += 1
        active_faults = RT.faults.snapshot_active()

        drop = _pick_drop(active_faults)
        if drop is not None and drop.spec.get("mode", "503") == "503":
            RT.fail += 1
            RT.last_error = "fault_drop_503"
            code = int(drop.spec.get("status_code", 503))
            raise HTTPException(status_code=code, detail="fault: drop 503")

        err_fault = _pick_error(active_faults)
        if err_fault is not None:
            RT.fail += 1
            RT.last_error = "fault_error"
            code = int(err_fault.spec.get("status_code", 500))
            msg = str(err_fault.spec.get("message", "fault: error"))
            return JSONResponse(
                status_code=code,
                content={"error": msg, "worker_id": WORKER_ID, "kind": "error"},
            )

        cfg = RT.cfg

    async with RT.lock:
        if RT.inflight >= cfg.capacity:
            RT.fail += 1
            RT.last_error = "over_capacity"
            raise HTTPException(status_code=503, detail="over capacity")
        RT.inflight += 1

    try:
        extra_delay_ms = _sum_delay_ms(active_faults)
        if extra_delay_ms > 0:
            await asyncio.sleep(extra_delay_ms / 1000.0)

        burn_ms = _sum_cpu_burn_ms(active_faults)
        if burn_ms > 0:
            await asyncio.to_thread(_busy_cpu, burn_ms)

        if drop is not None and drop.spec.get("mode") == "timeout":
            sleep_ms = int(drop.spec.get("sleep_ms", 5000))
            await asyncio.sleep(sleep_ms / 1000.0)
            async with RT.lock:
                RT.fail += 1
                RT.last_error = "fault_drop_timeout"
            raise HTTPException(status_code=504, detail="fault: timeout")

        jitter = random.randint(0, max(0, cfg.jitter_ms))
        simulated = cfg.base_lat_ms + jitter
        await asyncio.sleep(simulated / 1000.0)

        corrupt = _pick_corrupt(active_faults)
        if corrupt is not None:
            async with RT.lock:
                RT.fail += 1
                RT.last_error = "fault_corrupt"

            mode = corrupt.spec.get("mode", "invalid_json")
            if mode == "bad_fields":
                return JSONResponse(
                    status_code=500,
                    content={"worker": WORKER_ID, "msg": "CORRUPTED", "simulated_ms": "NaN"},
                )
            return PlainTextResponse(status_code=500, content="CORRUPTED")

        async with RT.lock:
            RT.ok += 1
            RT.last_simulated_ms = simulated
            RT.last_completed_at = time.time()
            RT.last_error = None

        return WorkResponse(
            worker_id=WORKER_ID,
            message="Handled request (simulated).",
            simulated_ms=simulated,
        )

    except Exception as e:
        if not isinstance(e, HTTPException):
            async with RT.lock:
                RT.fail += 1
                RT.last_error = str(e)
        raise

    finally:
        async with RT.lock:
            RT.inflight = max(0, RT.inflight - 1)

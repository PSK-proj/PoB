from __future__ import annotations

import os
import time
import asyncio
import random
from dataclasses import dataclass, field
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field


app = FastAPI(title="Worker", version="0.3.0")

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


@app.post("/handle", response_model=WorkResponse)
async def handle(req: WorkRequest):
    async with RT.lock:
        RT.total += 1

        cfg = RT.cfg
        if RT.inflight >= cfg.capacity:
            RT.fail += 1
            RT.last_error = "over_capacity"
            raise HTTPException(status_code=503, detail="over capacity")

        RT.inflight += 1
        base_lat_ms = cfg.base_lat_ms
        jitter_ms = cfg.jitter_ms

    try:
        jitter = random.randint(0, max(0, jitter_ms))
        simulated = base_lat_ms + jitter
        await asyncio.sleep(simulated / 1000.0)

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
        async with RT.lock:
            RT.fail += 1
            RT.last_error = str(e)
        raise

    finally:
        async with RT.lock:
            RT.inflight = max(0, RT.inflight - 1)

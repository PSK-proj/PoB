import os
import time
import asyncio
import random
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="Worker", version="0.2.0")

WORKER_ID = os.getenv("WORKER_ID", "worker-unknown")
BASE_LAT_MS = int(os.getenv("BASE_LAT_MS", "20"))
JITTER_MS = int(os.getenv("JITTER_MS", "5"))
CAPACITY = int(os.getenv("CAPACITY", "50"))
WEIGHT = int(os.getenv("WEIGHT", "1"))

_inflight = 0
_lock = asyncio.Lock()

_total = 0
_ok = 0
_fail = 0
_last_error: str | None = None
_last_simulated_ms: int | None = None
_last_completed_at: float | None = None


class WorkRequest(BaseModel):
    payload: dict | None = None


class WorkResponse(BaseModel):
    worker_id: str
    message: str
    simulated_ms: int


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "worker_id": WORKER_ID,
        "base_lat_ms": BASE_LAT_MS,
        "jitter_ms": JITTER_MS,
        "capacity": CAPACITY,
        "weight": WEIGHT,
    }


@app.get("/metrics")
async def metrics():
    async with _lock:
        return {
            "worker_id": WORKER_ID,
            "inflight": _inflight,
            "total": _total,
            "ok": _ok,
            "fail": _fail,
            "last_error": _last_error,
            "last_simulated_ms": _last_simulated_ms,
            "last_completed_at": _last_completed_at,
        }


@app.post("/handle", response_model=WorkResponse)
async def handle(req: WorkRequest):
    global _inflight, _total, _ok, _fail, _last_error, _last_simulated_ms, _last_completed_at

    async with _lock:
        _total += 1
        if _inflight >= CAPACITY:
            _fail += 1
            _last_error = "over_capacity"
            raise HTTPException(status_code=503, detail="over capacity")
        _inflight += 1

    try:
        jitter = random.randint(0, max(0, JITTER_MS))
        simulated = BASE_LAT_MS + jitter
        await asyncio.sleep(simulated / 1000.0)

        async with _lock:
            _ok += 1
            _last_simulated_ms = simulated
            _last_completed_at = time.time()

        return WorkResponse(
            worker_id=WORKER_ID,
            message="Handled request (simulated).",
            simulated_ms=simulated,
        )
    except Exception as e:
        async with _lock:
            _fail += 1
            _last_error = str(e)
        raise
    finally:
        async with _lock:
            _inflight = max(0, _inflight - 1)

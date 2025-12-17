import os
import time
import asyncio
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field


LB_URL = os.getenv("LB_URL", "http://lb:8000").rstrip("/")

app = FastAPI(title="Client Generator", version="0.1.0")


class StartRequest(BaseModel):
    rps: float = Field(ge=0.1, le=5000, description="Target requests per second")
    duration_sec: Optional[float] = Field(default=None, ge=0.1)
    endpoint: str = Field(default="/request")
    profile: str = Field(default="constant")


class StatusResponse(BaseModel):
    running: bool
    rps: Optional[float] = None
    duration_sec: Optional[float] = None
    profile: Optional[str] = None
    endpoint: Optional[str] = None
    started_at: Optional[float] = None
    total_sent: int
    total_ok: int
    total_fail: int
    last_error: Optional[str] = None


class _State:
    running: bool = False
    task: Optional[asyncio.Task] = None
    started_at: Optional[float] = None
    rps: Optional[float] = None
    duration_sec: Optional[float] = None
    profile: Optional[str] = None
    endpoint: Optional[str] = None
    total_sent: int = 0
    total_ok: int = 0
    total_fail: int = 0
    last_error: Optional[str] = None


STATE = _State()


@app.get("/health")
def health():
    return {"status": "ok", "service": "clientgen"}


@app.get("/status", response_model=StatusResponse)
def status():
    return StatusResponse(
        running=STATE.running,
        rps=STATE.rps,
        duration_sec=STATE.duration_sec,
        profile=STATE.profile,
        endpoint=STATE.endpoint,
        started_at=STATE.started_at,
        total_sent=STATE.total_sent,
        total_ok=STATE.total_ok,
        total_fail=STATE.total_fail,
        last_error=STATE.last_error,
    )


@app.post("/start")
async def start(req: StartRequest):
    if STATE.running:
        raise HTTPException(status_code=409, detail="Clientgen already running")

    STATE.running = True
    STATE.started_at = time.time()
    STATE.rps = req.rps
    STATE.duration_sec = req.duration_sec
    STATE.profile = req.profile
    STATE.endpoint = req.endpoint
    STATE.last_error = None

    STATE.task = asyncio.create_task(_traffic_loop(req))
    return {"ok": True, "message": "started", "config": req.model_dump()}


@app.post("/stop")
async def stop():
    if not STATE.running:
        return {"ok": True, "message": "already stopped"}

    STATE.running = False
    if STATE.task:
        STATE.task.cancel()
        try:
            await STATE.task
        except asyncio.CancelledError:
            pass
        finally:
            STATE.task = None

    return {"ok": True, "message": "stopped"}


async def _traffic_loop(req: StartRequest):
    interval = 1.0 / req.rps
    deadline = None
    if req.duration_sec is not None:
        deadline = time.monotonic() + req.duration_sec

    url = f"{LB_URL}{req.endpoint}"
    timeout = httpx.Timeout(2.0)

    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            while STATE.running:
                if deadline is not None and time.monotonic() >= deadline:
                    break

                t0 = time.monotonic()
                STATE.total_sent += 1

                try:
                    resp = await client.post(url, json={})
                    if 200 <= resp.status_code < 300:
                        STATE.total_ok += 1
                    else:
                        STATE.total_fail += 1
                        STATE.last_error = f"HTTP {resp.status_code}"
                except Exception as e:
                    STATE.total_fail += 1
                    STATE.last_error = str(e)

                elapsed = time.monotonic() - t0
                sleep_for = interval - elapsed
                if sleep_for > 0:
                    await asyncio.sleep(sleep_for)
        finally:
            STATE.running = False
            STATE.task = None

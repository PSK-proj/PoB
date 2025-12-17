from __future__ import annotations

import time
from typing import Any, Tuple

import httpx

from lb.core.registry import WorkerState


async def fetch_health(client: httpx.AsyncClient, worker: WorkerState) -> dict:
    r = await client.get(f"{worker.url}/health")
    r.raise_for_status()
    return r.json()


async def forward_handle(
    client: httpx.AsyncClient,
    worker: WorkerState,
    payload: dict,
    timeout_sec: float,
) -> Tuple[int, Any, float]:
    t0 = time.monotonic()
    r = await client.post(f"{worker.url}/handle", json=payload, timeout=timeout_sec)
    latency_ms = (time.monotonic() - t0) * 1000.0
    body: Any
    try:
        body = r.json()
    except Exception:
        body = {"raw": r.text}
    return r.status_code, body, latency_ms

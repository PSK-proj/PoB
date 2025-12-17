from __future__ import annotations

import asyncio
from typing import Any, Dict

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter(tags=["stream"])


def _state_snapshot(app) -> Dict[str, Any]:
    rt = app.state.rt

    total_assigned = sum(w.assigned for w in rt.workers)
    total_ok = sum(w.ok for w in rt.workers)
    total_fail = sum(w.fail for w in rt.workers)

    workers = []
    for w in rt.workers:
        workers.append(
            {
                "id": w.id,
                "url": w.url,
                "online": w.online,
                "reported_weight": w.reported_weight,
                "manual_weight": w.manual_weight,
                "auto_weight": w.auto_weight,
                "effective_weight": w.effective_weight,
                "assigned": w.assigned,
                "assigned_pct": (w.assigned / total_assigned * 100.0) if total_assigned > 0 else 0.0,
                "ok": w.ok,
                "fail": w.fail,
                "avg_latency_ms": w.avg_latency_ms,
                "last_error": w.last_error,
                "last_seen": w.last_seen if w.last_seen > 0 else None,
            }
        )

    return {
        "type": "state",
        "payload": {
            "weight_mode": rt.weight_mode,
            "total_assigned": total_assigned,
            "total_ok": total_ok,
            "total_fail": total_fail,
            "workers": workers,
        },
    }


@router.websocket("/stream")
async def stream(ws: WebSocket):
    await ws.accept()

    interval = float(getattr(ws.app.state, "stream_interval_sec", 0.5))

    try:
        while True:
            await ws.send_json(_state_snapshot(ws.app))
            await asyncio.sleep(interval)
    except WebSocketDisconnect:
        return

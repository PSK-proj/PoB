from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from lb.stream.state_stream import router as stream_router
from lb.core.registry import WorkerState
from lb.core.smooth_wrr import SmoothWRR


def test_stream_sends_state_snapshot():
    app = FastAPI()
    app.include_router(stream_router)

    w = WorkerState(id="worker-1", url="http://worker1:8000", reported_weight=5)
    w.recompute_effective("manual")

    rt = SimpleNamespace(
        workers=[w],
        balancer=SmoothWRR([w]),
        weight_mode="manual",
    )
    app.state.rt = rt
    app.state.stream_interval_sec = 999.0

    c = TestClient(app)
    with c.websocket_connect("/stream") as ws:
        msg = ws.receive_json()

    assert msg["type"] == "state"
    payload = msg["payload"]
    assert payload["weight_mode"] == "manual"
    assert isinstance(payload["workers"], list)
    assert payload["workers"][0]["id"] == "worker-1"

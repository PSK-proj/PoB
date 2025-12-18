from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from lb.core.registry import WorkerState
from lb.core.smooth_wrr import SmoothWRR
import lb.control.worker_config as wc


def test_patch_worker_config_syncs_lb_state(monkeypatch):
    app = FastAPI()
    app.include_router(wc.router)

    w = WorkerState(id="worker-1", url="http://worker1:8000", reported_weight=5)
    w.recompute_effective("manual")

    rt = SimpleNamespace(
        workers=[w],
        balancer=SmoothWRR([w]),
        weight_mode="manual",
        http=object(),
    )
    app.state.rt = rt

    async def fake_patch_config(_http, _worker, _payload):
        return {"base_lat_ms": 33, "jitter_ms": 5, "capacity": 50, "weight": 9}

    monkeypatch.setattr(wc, "api_patch_config", fake_patch_config)

    c = TestClient(app)
    r = c.patch("/workers/worker-1/config", json={"weight": 9, "base_lat_ms": 33})
    assert r.status_code == 200
    assert r.json()["weight"] == 9

    assert w.reported_weight == 9
    assert w.reported_base_lat_ms == 33
    assert w.effective_weight == 9

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from lb.control.weights import router as weights_router
from lb.core.registry import WorkerState
from lb.core.smooth_wrr import SmoothWRR


def _mk_app():
    app = FastAPI()
    app.include_router(weights_router)

    w1 = WorkerState(id="worker-1", url="http://worker1:8000", reported_weight=5)
    w2 = WorkerState(id="worker-2", url="http://worker2:8000", reported_weight=3)
    for w in (w1, w2):
        w.recompute_effective("manual")

    rt = SimpleNamespace(
        workers=[w1, w2],
        balancer=SmoothWRR([w1, w2]),
        weight_mode="manual",
    )
    app.state.rt = rt
    return app


def test_weight_mode_get_set():
    app = _mk_app()
    c = TestClient(app)

    r = c.get("/lb/weight-mode")
    assert r.status_code == 200
    assert r.json()["mode"] == "manual"

    r = c.post("/lb/weight-mode", json={"mode": "auto"})
    assert r.status_code == 200
    assert r.json()["mode"] == "auto"


def test_set_and_clear_manual_weight():
    app = _mk_app()
    c = TestClient(app)

    r = c.patch("/workers/worker-1/manual-weight", json={"weight": 12})
    assert r.status_code == 200
    assert r.json()["manual_weight"] == 12
    assert r.json()["effective_weight"] >= 1

    r = c.delete("/workers/worker-1/manual-weight")
    assert r.status_code == 200
    assert r.json()["manual_weight"] is None


def test_manual_weight_rejected_in_auto_mode():
    app = _mk_app()
    app.state.rt.weight_mode = "auto"
    c = TestClient(app)

    r = c.patch("/workers/worker-1/manual-weight", json={"weight": 3})
    assert r.status_code == 409


def test_manual_weight_missing_worker():
    app = _mk_app()
    c = TestClient(app)

    r = c.patch("/workers/no/manual-weight", json={"weight": 3})
    assert r.status_code == 404

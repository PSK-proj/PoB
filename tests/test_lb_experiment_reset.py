import asyncio
from collections import deque
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from lb.control import experiment
from lb.core.registry import WorkerState


def _mk_app(rt):
    app = FastAPI()
    app.include_router(experiment.router)
    app.state.rt = rt
    return app


def test_experiment_reset_clears_lb_state_and_history(monkeypatch):
    async def fake_clientgen_post(_path, _payload):
        return {"ok": True}

    async def fake_worker_reset(_http, worker):
        if worker.id == "w2":
            raise RuntimeError("boom")
        return {"ok": True}

    monkeypatch.setattr(experiment, "clientgen_post", fake_clientgen_post)
    monkeypatch.setattr(experiment, "worker_reset_metrics", fake_worker_reset)

    w1 = WorkerState(id="w1", url="http://w1:8000", reported_weight=1)
    w2 = WorkerState(id="w2", url="http://w2:8000", reported_weight=1)
    for w in (w1, w2):
        w.assigned = 5
        w.ok = 4
        w.fail = 1
        w.avg_latency_ms = 12.5
        w.current_weight = 3
        w.disabled_until = 123.0
        w.last_error = "err"
        w.online = True

    rt = SimpleNamespace(
        workers=[w1, w2],
        balancer=SimpleNamespace(lock=asyncio.Lock()),
        http=object(),
        history=deque([{"ts": 1, "state": {}}]),
        history_lock=asyncio.Lock(),
    )

    c = TestClient(_mk_app(rt))
    r = c.post("/experiment/reset")
    assert r.status_code == 200

    payload = r.json()
    assert payload["ok"] is False
    assert any(x["target"] == "lb" and x["id"] == "history" and x["ok"] for x in payload["results"])

    for w in (w1, w2):
        assert w.assigned == 0
        assert w.ok == 0
        assert w.fail == 0
        assert w.avg_latency_ms == 0.0
        assert w.current_weight == 0
        assert w.disabled_until == 0.0
        assert w.last_error is None

    assert list(rt.history) == []

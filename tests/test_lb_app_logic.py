import asyncio
from collections import deque
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import lb.app as lbapp
from lb.core.registry import WorkerState


class SeqBalancer:
    def __init__(self, workers):
        self._workers = list(workers)
        self._idx = 0

    async def choose(self):
        w = self._workers[min(self._idx, len(self._workers) - 1)]
        self._idx += 1
        w.assigned += 1
        return w


@pytest.mark.asyncio
async def test_handle_request_success_updates_stats(monkeypatch):
    w = WorkerState(id="w1", url="http://w1:8000")
    rt = SimpleNamespace(workers=[w], balancer=SeqBalancer([w]), http=object(), weight_mode="manual")
    lbapp.app.state.rt = rt

    async def fake_forward(_http, _worker, payload, timeout_sec):
        return 200, {"ok": True, "payload": payload}, 12.345

    monkeypatch.setattr(lbapp, "forward_handle", fake_forward)

    resp = await lbapp.handle_request(lbapp.LBRequest(payload={"x": 1}))
    assert resp.worker_status == 200
    assert w.ok == 1
    assert w.fail == 0
    assert w.last_error is None


@pytest.mark.asyncio
async def test_handle_request_retries_and_disables_on_5xx(monkeypatch):
    monkeypatch.setattr(lbapp, "RETRY_ATTEMPTS", 2)
    monkeypatch.setattr(lbapp, "DISABLE_ON_FAIL_SEC", 5.0)
    monkeypatch.setattr(lbapp.time, "time", lambda: 100.0)

    w1 = WorkerState(id="w1", url="http://w1:8000")
    w2 = WorkerState(id="w2", url="http://w2:8000")
    rt = SimpleNamespace(workers=[w1, w2], balancer=SeqBalancer([w1, w2]), http=object(), weight_mode="manual")
    lbapp.app.state.rt = rt

    responses = [(500, {"err": True}, 10.0), (200, {"ok": True}, 5.0)]

    async def fake_forward(_http, _worker, payload, timeout_sec):
        return responses.pop(0)

    monkeypatch.setattr(lbapp, "forward_handle", fake_forward)

    resp = await lbapp.handle_request(lbapp.LBRequest(payload={}))
    assert resp.chosen_worker == "w2"
    assert w1.fail == 1
    assert w1.disabled_until == 105.0
    assert w2.ok == 1


@pytest.mark.asyncio
async def test_handle_request_all_attempts_fail(monkeypatch):
    monkeypatch.setattr(lbapp, "RETRY_ATTEMPTS", 1)

    w = WorkerState(id="w1", url="http://w1:8000")
    rt = SimpleNamespace(workers=[w], balancer=SeqBalancer([w]), http=object(), weight_mode="manual")
    lbapp.app.state.rt = rt

    async def fake_forward(_http, _worker, payload, timeout_sec):
        raise RuntimeError("boom")

    monkeypatch.setattr(lbapp, "forward_handle", fake_forward)

    with pytest.raises(HTTPException) as exc:
        await lbapp.handle_request(lbapp.LBRequest(payload={}))

    assert exc.value.status_code == 502
    assert w.fail == 1


def test_compute_auto_weights_prefers_low_latency(monkeypatch):
    monkeypatch.setattr(lbapp, "AUTO_WEIGHT_MAX", 10)

    w_fast = WorkerState(id="fast", url="http://fast:8000")
    w_slow = WorkerState(id="slow", url="http://slow:8000")
    for w in (w_fast, w_slow):
        w.online = True
        w.ok = 9
        w.fail = 1

    w_fast.avg_latency_ms = 10.0
    w_slow.avg_latency_ms = 100.0

    rt = SimpleNamespace(workers=[w_fast, w_slow])
    lbapp._compute_auto_weights(rt)

    assert w_fast.auto_weight > w_slow.auto_weight


@pytest.mark.asyncio
async def test_record_history_trims_old_samples(monkeypatch):
    monkeypatch.setattr(lbapp, "LB_HISTORY_WINDOW_MS", 1000)
    monkeypatch.setattr(lbapp, "LB_HISTORY_SAMPLE_SEC", 1.0)

    w = WorkerState(id="w1", url="http://w1:8000")
    w.recompute_effective("manual")

    rt = SimpleNamespace(
        workers=[w],
        weight_mode="manual",
        history=deque(),
        history_lock=asyncio.Lock(),
    )

    times = [1.0, 3.0]
    monkeypatch.setattr(lbapp.time, "time", lambda: times.pop(0))

    await lbapp._record_history(rt)
    await lbapp._record_history(rt)

    assert len(rt.history) == 1
    assert rt.history[0].ts == 3000

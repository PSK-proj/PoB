import asyncio

from fastapi.testclient import TestClient
import pytest

import clientgen.app as cg


async def _fake_traffic_loop(_req):
    while cg.STATE.running:
        await asyncio.sleep(0.01)


def _reset_state():
    cg.STATE.running = False
    cg.STATE.task = None
    cg.STATE.started_at = None
    cg.STATE.rps = None
    cg.STATE.duration_sec = None
    cg.STATE.profile = None
    cg.STATE.endpoint = None
    cg.STATE.concurrency = None
    cg.STATE.total_sent = 0
    cg.STATE.total_ok = 0
    cg.STATE.total_fail = 0
    cg.STATE.last_error = None


def test_start_stop_status_flow(monkeypatch):
    monkeypatch.setattr(cg, "_traffic_loop", _fake_traffic_loop)
    client = TestClient(cg.app)

    client.post("/reset")

    payload = {
        "rps": 25,
        "duration_sec": 1,
        "endpoint": "/request",
        "profile": "constant",
        "concurrency": 5,
    }
    r = client.post("/start", json=payload)
    assert r.status_code == 200

    status = client.get("/status").json()
    assert status["running"] is True
    assert status["rps"] == 25
    assert status["concurrency"] == 5

    r = client.post("/start", json=payload)
    assert r.status_code == 409

    client.post("/stop")
    status = client.get("/status").json()
    assert status["running"] is False


def test_reset_clears_counters(monkeypatch):
    monkeypatch.setattr(cg, "_traffic_loop", _fake_traffic_loop)
    client = TestClient(cg.app)

    cg.STATE.total_sent = 10
    cg.STATE.total_ok = 7
    cg.STATE.total_fail = 3
    cg.STATE.rps = 5
    cg.STATE.concurrency = 2

    r = client.post("/reset")
    assert r.status_code == 200

    status = client.get("/status").json()
    assert status["total_sent"] == 0
    assert status["total_ok"] == 0
    assert status["total_fail"] == 0
    assert status["rps"] is None
    assert status["concurrency"] is None


def test_health_and_stop_when_idle():
    _reset_state()
    client = TestClient(cg.app)

    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["service"] == "clientgen"

    r = client.post("/stop")
    assert r.status_code == 200
    assert r.json()["message"] == "already stopped"


@pytest.mark.asyncio
async def test_send_one_tracks_ok_and_failures():
    _reset_state()

    class OkClient:
        async def post(self, _url, json=None):
            return type("Resp", (), {"status_code": 204})()

    sem = asyncio.Semaphore(0)
    await cg._send_one(OkClient(), "http://x", sem)
    await asyncio.wait_for(sem.acquire(), 0.1)
    assert cg.STATE.total_sent == 1
    assert cg.STATE.total_ok == 1
    assert cg.STATE.total_fail == 0

    _reset_state()

    class FailClient:
        async def post(self, _url, json=None):
            return type("Resp", (), {"status_code": 500})()

    sem = asyncio.Semaphore(0)
    await cg._send_one(FailClient(), "http://x", sem)
    await asyncio.wait_for(sem.acquire(), 0.1)
    assert cg.STATE.total_fail == 1
    assert cg.STATE.last_error == "HTTP 500"

    _reset_state()

    class ErrClient:
        async def post(self, _url, json=None):
            raise RuntimeError("boom")

    sem = asyncio.Semaphore(0)
    await cg._send_one(ErrClient(), "http://x", sem)
    await asyncio.wait_for(sem.acquire(), 0.1)
    assert cg.STATE.total_fail == 1
    assert cg.STATE.last_error == "boom"


@pytest.mark.asyncio
async def test_traffic_loop_respects_deadline_and_sleep(monkeypatch):
    _reset_state()
    cg.STATE.running = True

    sleep_calls = []

    async def fake_sleep(delay):
        sleep_calls.append(delay)

    async def fake_send_one(_client, _url, sem):
        cg.STATE.total_sent += 1
        cg.STATE.total_ok += 1
        sem.release()

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(cg.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(cg, "_send_one", fake_send_one)
    monkeypatch.setattr(cg.httpx, "AsyncClient", lambda *a, **k: FakeClient())

    ticks = iter([0.0, 0.0, 0.01, 0.02, 0.2])
    monkeypatch.setattr(cg.time, "monotonic", lambda: next(ticks, 0.2))

    req = cg.StartRequest(
        rps=10, duration_sec=0.1, endpoint="/request", profile="constant", concurrency=1
    )
    await cg._traffic_loop(req)

    assert cg.STATE.running is False
    assert cg.STATE.total_sent == 1
    assert sleep_calls and sleep_calls[0] > 0


@pytest.mark.asyncio
async def test_traffic_loop_cancellation_cleans_up(monkeypatch):
    _reset_state()
    cg.STATE.running = True
    started = asyncio.Event()
    sleep_event = asyncio.Event()

    async def fake_send_one(_client, _url, sem):
        started.set()
        try:
            await sleep_event.wait()
        finally:
            sem.release()

    async def fake_sleep(_delay):
        await sleep_event.wait()

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(cg, "_send_one", fake_send_one)
    monkeypatch.setattr(cg.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(cg.httpx, "AsyncClient", lambda *a, **k: FakeClient())
    monkeypatch.setattr(cg.time, "monotonic", lambda: 0.0)

    req = cg.StartRequest(
        rps=1, duration_sec=None, endpoint="/request", profile="constant", concurrency=1
    )
    task = asyncio.create_task(cg._traffic_loop(req))
    await asyncio.wait_for(started.wait(), 1)

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert cg.STATE.running is False

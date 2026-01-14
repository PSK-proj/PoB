from fastapi import FastAPI
from fastapi.testclient import TestClient
import httpx

import lb.control.traffic as traffic


def _mk_app():
    app = FastAPI()
    app.include_router(traffic.router)
    return app


def test_start_forwards_payload(monkeypatch):
    sent = {}

    async def fake_post(path, payload):
        sent["path"] = path
        sent["payload"] = payload
        return {"ok": True}

    monkeypatch.setattr(traffic, "post", fake_post)

    c = TestClient(_mk_app())
    r = c.post(
        "/traffic/start",
        json={
            "rps": 5,
            "duration_sec": 1,
            "endpoint": "/request",
            "profile": "constant",
            "concurrency": 10,
        },
    )
    assert r.status_code == 200
    assert sent["path"] == "/start"
    assert sent["payload"]["concurrency"] == 10


def test_start_409_from_clientgen(monkeypatch):
    req = httpx.Request("POST", "http://clientgen/start")
    resp = httpx.Response(409, json={"detail": "Clientgen already running"})

    async def fake_post(_path, _payload):
        raise httpx.HTTPStatusError("boom", request=req, response=resp)

    monkeypatch.setattr(traffic, "post", fake_post)

    c = TestClient(_mk_app())
    r = c.post(
        "/traffic/start",
        json={"rps": 5, "duration_sec": 1, "endpoint": "/request", "profile": "constant"},
    )
    assert r.status_code == 409
    assert r.json()["detail"] == "Clientgen already running"


def test_stop_propagates_upstream_errors(monkeypatch):
    async def fake_post(_path, _payload):
        raise httpx.HTTPError("down")

    monkeypatch.setattr(traffic, "post", fake_post)

    c = TestClient(_mk_app())
    r = c.post("/traffic/stop")
    assert r.status_code == 502


def test_status_propagates_upstream_errors(monkeypatch):
    async def fake_get(_path):
        raise httpx.HTTPError("down")

    monkeypatch.setattr(traffic, "get", fake_get)

    c = TestClient(_mk_app())
    r = c.get("/traffic/status")
    assert r.status_code == 502

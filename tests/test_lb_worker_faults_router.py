from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
import httpx

from lb.control import worker_faults
from lb.core.registry import WorkerState


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            req = httpx.Request("GET", "http://upstream")
            resp = httpx.Response(self.status_code, request=req)
            raise httpx.HTTPStatusError("upstream", request=req, response=resp)

    def json(self):
        return self._payload


class FakeHttp:
    def __init__(self, response):
        self.response = response
        self.calls = []

    async def get(self, url):
        self.calls.append(("get", url))
        return self.response

    async def post(self, url, json=None):
        self.calls.append(("post", url, json))
        return self.response

    async def delete(self, url):
        self.calls.append(("delete", url))
        return self.response


def _mk_app(rt):
    app = FastAPI()
    app.include_router(worker_faults.router)
    app.state.rt = rt
    return app


def test_list_faults_proxies_to_worker():
    payload = [{"id": "f1", "kind": "delay", "created_at": 1.0, "expires_at": None, "spec": {}}]
    http = FakeHttp(FakeResponse(payload))
    w = WorkerState(id="w1", url="http://w1:8000")
    rt = SimpleNamespace(workers=[w], http=http)

    c = TestClient(_mk_app(rt))
    r = c.get("/workers/w1/faults")
    assert r.status_code == 200
    assert r.json() == payload
    assert http.calls[0] == ("get", "http://w1:8000/faults")


def test_add_fault_uses_payload():
    payload = {"id": "f2", "kind": "drop", "created_at": 1.0, "expires_at": None, "spec": {}}
    http = FakeHttp(FakeResponse(payload))
    w = WorkerState(id="w1", url="http://w1:8000")
    rt = SimpleNamespace(workers=[w], http=http)

    c = TestClient(_mk_app(rt))
    r = c.post("/workers/w1/faults", json={"kind": "drop"})
    assert r.status_code == 200
    assert http.calls[0][0] == "post"
    assert http.calls[0][1] == "http://w1:8000/faults"


def test_missing_worker_returns_404():
    http = FakeHttp(FakeResponse([]))
    rt = SimpleNamespace(workers=[], http=http)

    c = TestClient(_mk_app(rt))
    r = c.get("/workers/nope/faults")
    assert r.status_code == 404


def test_upstream_error_returns_502():
    http = FakeHttp(FakeResponse({"err": "x"}, status_code=500))
    w = WorkerState(id="w1", url="http://w1:8000")
    rt = SimpleNamespace(workers=[w], http=http)

    c = TestClient(_mk_app(rt))
    r = c.get("/workers/w1/faults")
    assert r.status_code == 502
    assert r.json()["detail"]["code"] == "upstream_error"

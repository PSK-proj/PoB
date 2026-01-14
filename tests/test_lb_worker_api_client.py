import pytest

import lb.clients.worker_api as worker_api
from lb.core.registry import WorkerState


class FakeResponse:
    def __init__(self, status_code=200, json_body=None, text="raw"):
        self.status_code = status_code
        self._json_body = json_body
        self.text = text
        self.raised = False

    def raise_for_status(self):
        self.raised = True

    def json(self):
        if self._json_body is None:
            raise ValueError("invalid json")
        return self._json_body


class FakeClient:
    def __init__(self, response):
        self.response = response
        self.calls = []

    async def post(self, url, json=None, timeout=None):
        self.calls.append(("post", url, json, timeout))
        return self.response


class FakeClientAll:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    async def get(self, url):
        self.calls.append(("get", url))
        return self.responses[url]

    async def post(self, url, json=None, timeout=None):
        self.calls.append(("post", url, json, timeout))
        return self.responses[url]

    async def patch(self, url, json=None):
        self.calls.append(("patch", url, json))
        return self.responses[url]

    async def delete(self, url):
        self.calls.append(("delete", url))
        return self.responses[url]


@pytest.mark.asyncio
async def test_forward_handle_returns_raw_on_non_json(monkeypatch):
    w = WorkerState(id="w1", url="http://w1:8000")
    resp = FakeResponse(status_code=500, json_body=None, text="ERR")
    client = FakeClient(resp)

    ticks = iter([1.0, 2.0])
    monkeypatch.setattr(worker_api.time, "monotonic", lambda: next(ticks, 2.0))

    status, body, ms = await worker_api.forward_handle(
        client, w, payload={"x": 1}, timeout_sec=1.5
    )

    assert status == 500
    assert body == {"raw": "ERR"}
    assert ms == 1000.0
    assert client.calls[0][0] == "post"
    assert client.calls[0][1] == "http://w1:8000/handle"


@pytest.mark.asyncio
async def test_forward_handle_returns_json_body(monkeypatch):
    w = WorkerState(id="w1", url="http://w1:8000")
    resp = FakeResponse(status_code=200, json_body={"ok": True}, text="")
    client = FakeClient(resp)

    ticks = iter([5.0, 5.5])
    monkeypatch.setattr(worker_api.time, "monotonic", lambda: next(ticks, 5.5))

    status, body, ms = await worker_api.forward_handle(
        client, w, payload={"x": 1}, timeout_sec=0.5
    )

    assert status == 200
    assert body == {"ok": True}
    assert ms == 500.0


@pytest.mark.asyncio
async def test_worker_api_basic_endpoints_call_urls():
    w = WorkerState(id="w1", url="http://w1:8000")
    responses = {
        "http://w1:8000/health": FakeResponse(json_body={"status": "ok"}),
        "http://w1:8000/metrics": FakeResponse(json_body={"total": 1}),
        "http://w1:8000/config": FakeResponse(json_body={"weight": 2}),
        "http://w1:8000/metrics/reset": FakeResponse(json_body={"ok": True}),
    }
    client = FakeClientAll(responses)

    assert await worker_api.fetch_health(client, w) == {"status": "ok"}
    assert await worker_api.fetch_metrics(client, w) == {"total": 1}
    assert await worker_api.get_config(client, w) == {"weight": 2}
    assert await worker_api.patch_config(client, w, {"weight": 5}) == {"weight": 2}
    assert await worker_api.reset_metrics(client, w) == {"ok": True}

    for url in responses:
        assert responses[url].raised is True

    assert client.calls == [
        ("get", "http://w1:8000/health"),
        ("get", "http://w1:8000/metrics"),
        ("get", "http://w1:8000/config"),
        ("patch", "http://w1:8000/config", {"weight": 5}),
        ("post", "http://w1:8000/metrics/reset", None, None),
    ]


@pytest.mark.asyncio
async def test_worker_api_faults_endpoints_call_urls():
    w = WorkerState(id="w1", url="http://w1:8000")
    responses = {
        "http://w1:8000/faults": FakeResponse(json_body=[{"id": "f1"}]),
        "http://w1:8000/faults/f1": FakeResponse(json_body={"ok": True}),
    }
    client = FakeClientAll(responses)

    assert await worker_api.list_faults(client, w) == [{"id": "f1"}]
    assert await worker_api.add_fault(client, w, {"kind": "drop"}) == [{"id": "f1"}]
    assert await worker_api.delete_fault(client, w, "f1") == {"ok": True}
    assert await worker_api.clear_faults(client, w) == [{"id": "f1"}]

    for url in responses:
        assert responses[url].raised is True

    assert client.calls == [
        ("get", "http://w1:8000/faults"),
        ("post", "http://w1:8000/faults", {"kind": "drop"}, None),
        ("delete", "http://w1:8000/faults/f1"),
        ("delete", "http://w1:8000/faults"),
    ]

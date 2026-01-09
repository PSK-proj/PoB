import pytest

import lb.clients.clientgen_api as cg


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


@pytest.mark.asyncio
async def test_clientgen_post_and_get(monkeypatch):
    calls = []

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.timeout = kwargs.get("timeout")

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json=None):
            calls.append(("post", url, json))
            return FakeResponse({"ok": True})

        async def get(self, url):
            calls.append(("get", url))
            return FakeResponse({"running": False})

    monkeypatch.setattr(cg, "CLIENTGEN_URL", "http://clientgen")
    monkeypatch.setattr(cg.httpx, "AsyncClient", FakeClient)

    post_resp = await cg.post("/start", {"rps": 1})
    get_resp = await cg.get("/status")

    assert post_resp["ok"] is True
    assert get_resp["running"] is False
    assert calls == [
        ("post", "http://clientgen/start", {"rps": 1}),
        ("get", "http://clientgen/status"),
    ]

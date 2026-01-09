from fastapi.testclient import TestClient

import worker.app as worker_app


c = TestClient(worker_app.app)


def _reset_worker():
    c.delete("/faults")
    c.post("/metrics/reset")
    c.patch(
        "/config",
        json={"base_lat_ms": 0, "jitter_ms": 0, "capacity": 1000, "weight": 1},
    )


def test_metrics_snapshot_and_reset_flow():
    _reset_worker()

    for _ in range(3):
        r = c.post("/handle", json={})
        assert r.status_code == 200

    m = c.get("/metrics").json()
    assert m["total"] == 3
    assert m["ok"] == 3
    assert m["fail"] == 0

    reset = c.post("/metrics/reset").json()
    assert reset["before"]["total"] == 3
    assert reset["after"]["total"] == 0


def test_config_patch_and_get():
    _reset_worker()
    r = c.patch("/config", json={"base_lat_ms": 33, "weight": 7})
    assert r.status_code == 200
    assert r.json()["base_lat_ms"] == 33
    assert r.json()["weight"] == 7

    cfg = c.get("/config").json()
    assert cfg["base_lat_ms"] == 33
    assert cfg["weight"] == 7


def test_over_capacity_returns_503_and_increments_fail():
    _reset_worker()
    c.patch("/config", json={"capacity": 1})

    worker_app.RT.inflight = 1
    try:
        r = c.post("/handle", json={})
        assert r.status_code == 503
    finally:
        worker_app.RT.inflight = 0

    m = c.get("/metrics").json()
    assert m["fail"] >= 1

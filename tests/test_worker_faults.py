import time
from fastapi.testclient import TestClient
from worker.app import app

c = TestClient(app)


def _clean():
    c.delete("/faults")
    c.post("/metrics/reset")
    c.patch("/config", json={"base_lat_ms": 0, "jitter_ms": 0, "capacity": 1000, "weight": 1})


def test_drop_503_fault():
    _clean()
    c.post("/faults", json={"kind": "drop", "mode": "503", "status_code": 503, "duration_sec": 5})
    r = c.post("/handle", json={})
    assert r.status_code == 503


def test_corrupt_invalid_json_returns_500_text():
    _clean()
    c.post("/faults", json={"kind": "corrupt", "mode": "invalid_json", "duration_sec": 5})
    r = c.post("/handle", json={})
    assert r.status_code == 500
    assert r.text == "CORRUPTED"


def test_fault_ttl_expires():
    _clean()
    c.post("/faults", json={"kind": "delay", "delay_ms": 10, "duration_sec": 0.1})
    time.sleep(0.2)
    r = c.get("/faults")
    assert r.status_code == 200
    assert r.json() == []


def test_error_fault_returns_json():
    _clean()
    c.post("/faults", json={"kind": "error", "status_code": 500, "message": "boom", "duration_sec": 5})
    r = c.post("/handle", json={})
    assert r.status_code == 500
    assert r.json()["error"] == "boom"

def test_cpu_burn_fault_still_handles():
    _clean()
    c.post("/faults", json={"kind": "cpu_burn", "burn_ms": 10, "duration_sec": 5})
    r = c.post("/handle", json={})
    assert r.status_code == 200
    assert r.json()["worker_id"]
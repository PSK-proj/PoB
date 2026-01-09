import worker.faults as wf
from worker.faults import (
    CpuBurnFaultCreate,
    DelayFaultCreate,
    DropFaultCreate,
    FaultRegistry,
    should_trigger,
)


def test_fault_registry_add_delete_clear_and_purge():
    reg = FaultRegistry()

    fv = reg.add(DelayFaultCreate(kind="delay", delay_ms=10, duration_sec=1))
    assert fv.kind == "delay"
    assert len(fv.id) == 12
    assert reg.delete("missing") is False
    assert reg.delete(fv.id) is True
    assert reg.list_views() == []

    fv = reg.add(DropFaultCreate(kind="drop", mode="503", status_code=503, duration_sec=1))
    reg.purge_expired(now=float(fv.expires_at) + 1.0)
    assert reg.list_views() == []

    reg.add(CpuBurnFaultCreate(kind="cpu_burn", burn_ms=5))
    reg.add(CpuBurnFaultCreate(kind="cpu_burn", burn_ms=10))
    assert reg.clear() == 2
    assert reg.list_views() == []


def test_should_trigger_probability_bounds(monkeypatch):
    assert should_trigger(1.0) is True
    assert should_trigger(0.0) is False

    monkeypatch.setattr(wf.random, "random", lambda: 0.4)
    assert should_trigger(0.5) is True

    monkeypatch.setattr(wf.random, "random", lambda: 0.6)
    assert should_trigger(0.5) is False

from lb.core.registry import WorkerState


def test_effective_weight_manual_prefers_manual_over_reported():
    w = WorkerState(id="w", url="http://w:8000", reported_weight=3)
    w.manual_weight = 10
    w.recompute_effective("manual")
    assert w.effective_weight == 10


def test_effective_weight_manual_falls_back_to_reported():
    w = WorkerState(id="w", url="http://w:8000", reported_weight=3)
    w.manual_weight = None
    w.recompute_effective("manual")
    assert w.effective_weight == 3


def test_effective_weight_auto_prefers_auto_over_reported():
    w = WorkerState(id="w", url="http://w:8000", reported_weight=3)
    w.auto_weight = 7
    w.recompute_effective("auto")
    assert w.effective_weight == 7


def test_effective_weight_auto_falls_back_to_reported():
    w = WorkerState(id="w", url="http://w:8000", reported_weight=3)
    w.auto_weight = None
    w.recompute_effective("auto")
    assert w.effective_weight == 3

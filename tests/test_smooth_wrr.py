import pytest

from lb.core.registry import WorkerState
from lb.core.smooth_wrr import SmoothWRR


@pytest.mark.asyncio
async def test_smooth_wrr_distribution_roughly_matches_weights():
    w1 = WorkerState(id="w1", url="http://w1:8000", reported_weight=5)
    w2 = WorkerState(id="w2", url="http://w2:8000", reported_weight=3)
    w3 = WorkerState(id="w3", url="http://w3:8000", reported_weight=2)

    for w in (w1, w2, w3):
        w.recompute_effective("manual")
        w.online = True
        w.disabled_until = 0.0

    b = SmoothWRR([w1, w2, w3])

    n = 5000
    for _ in range(n):
        chosen = await b.choose()
        assert chosen is not None

    total = w1.assigned + w2.assigned + w3.assigned
    assert total == n

    assert abs((w1.assigned / n) - (5 / 10)) < 0.03
    assert abs((w2.assigned / n) - (3 / 10)) < 0.03
    assert abs((w3.assigned / n) - (2 / 10)) < 0.03


@pytest.mark.asyncio
async def test_smooth_wrr_skips_offline_workers():
    w1 = WorkerState(id="w1", url="http://w1:8000", reported_weight=1)
    w2 = WorkerState(id="w2", url="http://w2:8000", reported_weight=1)

    for w in (w1, w2):
        w.recompute_effective("manual")
        w.online = True
        w.disabled_until = 0.0

    w2.online = False

    b = SmoothWRR([w1, w2])

    for _ in range(200):
        chosen = await b.choose()
        assert chosen is not None
        assert chosen.id == "w1"

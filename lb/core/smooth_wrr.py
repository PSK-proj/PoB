from __future__ import annotations

import asyncio
from typing import Optional

from .registry import WorkerState


class SmoothWRR:
    def __init__(self, workers: list[WorkerState]):
        self._workers = workers
        self._lock = asyncio.Lock()

    async def choose(self) -> Optional[WorkerState]:
        async with self._lock:
            eligible = [w for w in self._workers if w.eligible()]
            if not eligible:
                return None

            total = sum(w.weight for w in eligible)

            best: Optional[WorkerState] = None
            for w in eligible:
                w.current_weight += w.weight
                if best is None or w.current_weight > best.current_weight:
                    best = w

            assert best is not None
            best.current_weight -= total
            best.assigned += 1
            return best

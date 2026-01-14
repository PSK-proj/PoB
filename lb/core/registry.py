from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
import time


@dataclass
class WorkerState:
    id: str
    url: str

    reported_weight: int = 1
    manual_weight: Optional[int] = None
    auto_weight: Optional[int] = None
    effective_weight: int = 1

    current_weight: int = 0
    online: bool = True
    disabled_until: float = 0.0

    assigned: int = 0
    ok: int = 0
    fail: int = 0
    avg_latency_ms: float = 0.0
    recent_latency_ms: float = 0.0
    recent_fail_rate: float = 0.0
    last_error: Optional[str] = None
    last_seen: float = 0.0
    reported_base_lat_ms: Optional[int] = None

    def eligible(self) -> bool:
        return self.online and self.effective_weight > 0 and time.time() >= self.disabled_until

    def recompute_effective(self, mode: str) -> None:
        if mode == "manual":
            w = self.manual_weight if self.manual_weight is not None else self.reported_weight
        elif mode == "auto":
            w = self.auto_weight if self.auto_weight is not None else self.reported_weight
        else:
            w = self.reported_weight
        self.effective_weight = max(1, int(w))

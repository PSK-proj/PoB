from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
import time


@dataclass
class WorkerState:
    id: str
    url: str
    weight: int = 1

    current_weight: int = 0
    online: bool = True
    disabled_until: float = 0.0

    assigned: int = 0
    ok: int = 0
    fail: int = 0
    avg_latency_ms: float = 0.0
    last_error: Optional[str] = None
    last_seen: float = 0.0

    def eligible(self) -> bool:
        return self.online and self.weight > 0 and time.time() >= self.disabled_until

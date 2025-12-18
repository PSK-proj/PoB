from __future__ import annotations

import time
import uuid
import random
from dataclasses import dataclass
from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, Field


class DelayFaultCreate(BaseModel):
    kind: Literal["delay"]
    delay_ms: int = Field(ge=0, le=60_000)
    probability: float = Field(default=1.0, ge=0.0, le=1.0)
    duration_sec: float | None = Field(default=None, ge=0.1, le=86_400)


class DropFaultCreate(BaseModel):
    kind: Literal["drop"]
    mode: Literal["503", "timeout"] = "503"
    status_code: int = Field(default=503, ge=400, le=599)
    sleep_ms: int = Field(default=5000, ge=1, le=600_000)
    probability: float = Field(default=1.0, ge=0.0, le=1.0)
    duration_sec: float | None = Field(default=None, ge=0.1, le=86_400)


class CorruptFaultCreate(BaseModel):
    kind: Literal["corrupt"]
    mode: Literal["invalid_json", "bad_fields"] = "invalid_json"
    probability: float = Field(default=1.0, ge=0.0, le=1.0)
    duration_sec: float | None = Field(default=None, ge=0.1, le=86_400)


FaultCreate = Annotated[
    Union[DelayFaultCreate, DropFaultCreate, CorruptFaultCreate],
    Field(discriminator="kind"),
]


class FaultView(BaseModel):
    id: str
    kind: str
    created_at: float
    expires_at: float | None
    spec: dict


@dataclass
class Fault:
    id: str
    kind: str
    created_at: float
    expires_at: float | None
    spec: dict


class FaultRegistry:
    def __init__(self) -> None:
        self._faults: list[Fault] = []

    def purge_expired(self, now: float | None = None) -> None:
        if now is None:
            now = time.time()
        self._faults = [f for f in self._faults if (f.expires_at is None or f.expires_at > now)]

    def list_views(self) -> list[FaultView]:
        self.purge_expired()
        return [FaultView(id=f.id, kind=f.kind, created_at=f.created_at, expires_at=f.expires_at, spec=f.spec) for f in self._faults]

    def add(self, fc: FaultCreate) -> FaultView:
        now = time.time()
        expires_at = None
        duration = getattr(fc, "duration_sec", None)
        if duration is not None:
            expires_at = now + float(duration)

        fid = uuid.uuid4().hex[:12]
        spec = fc.model_dump()
        f = Fault(id=fid, kind=spec["kind"], created_at=now, expires_at=expires_at, spec=spec)
        self._faults.append(f)
        return FaultView(id=f.id, kind=f.kind, created_at=f.created_at, expires_at=f.expires_at, spec=f.spec)

    def delete(self, fault_id: str) -> bool:
        before = len(self._faults)
        self._faults = [f for f in self._faults if f.id != fault_id]
        return len(self._faults) != before

    def clear(self) -> int:
        n = len(self._faults)
        self._faults.clear()
        return n

    def snapshot_active(self) -> list[Fault]:
        self.purge_expired()
        return list(self._faults)


def should_trigger(probability: float) -> bool:
    if probability >= 1.0:
        return True
    if probability <= 0.0:
        return False
    return random.random() < probability

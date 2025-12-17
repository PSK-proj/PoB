from fastapi import FastAPI
from pydantic import BaseModel
from typing import List
import itertools

from lb.control.traffic import router as traffic_router

app = FastAPI(title="Load Balancer", version="0.1.0")
app.include_router(traffic_router)


class WorkerConfig(BaseModel):
    id: str
    weight: int = 1
    online: bool = True


class RequestResult(BaseModel):
    chosen_worker: str
    note: str = "Simulation only – forwarding to real worker not implemented yet."


workers: List[WorkerConfig] = [
    WorkerConfig(id="worker-1", weight=1),
    WorkerConfig(id="worker-2", weight=1),
]

_rr_cycle = itertools.cycle(range(len(workers)))


@app.get("/health")
def health():
    return {"status": "ok", "service": "lb"}


@app.get("/workers", response_model=List[WorkerConfig])
def list_workers():
    return workers


@app.post("/request", response_model=RequestResult)
def handle_request():
    idx = next(_rr_cycle)
    worker = workers[idx]
    return RequestResult(chosen_worker=worker.id)

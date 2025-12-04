from fastapi import FastAPI
from pydantic import BaseModel
import os

app = FastAPI(title="Worker", version="0.1.0")

WORKER_ID = os.getenv("WORKER_ID", "worker-unknown")


class WorkRequest(BaseModel):
    payload: dict | None = None


class WorkResponse(BaseModel):
    worker_id: str
    message: str


@app.get("/health")
def health():
    return {"status": "ok", "worker_id": WORKER_ID}


@app.post("/handle", response_model=WorkResponse)
def handle(req: WorkRequest):
    return WorkResponse(worker_id=WORKER_ID, message="Handled request (stub).")

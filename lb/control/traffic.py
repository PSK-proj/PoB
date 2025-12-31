from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
import httpx

from lb.clients.clientgen_api import post, get

router = APIRouter(prefix="/traffic", tags=["traffic"])


class TrafficStart(BaseModel):
    rps: float = Field(ge=0.1, le=5000)
    duration_sec: float | None = Field(default=None, ge=0.1)
    endpoint: str = "/request"
    profile: str = "constant"


@router.post("/start")
async def start(payload: TrafficStart):
    try:
        return await post("/start", payload.model_dump())
    except httpx.HTTPStatusError as e:
        if e.response is not None and e.response.status_code == 409:
            detail = None
            try:
                body = e.response.json()
                if isinstance(body, dict):
                    detail = body.get("detail")
            except Exception:
                detail = None
            if not detail:
                detail = "Clientgen already running"
            raise HTTPException(status_code=409, detail=detail)
        raise HTTPException(status_code=502, detail=f"clientgen error: {e}")
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"clientgen error: {e}")


@router.post("/stop")
async def stop():
    try:
        return await post("/stop", None)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"clientgen error: {e}")


@router.get("/status")
async def status():
    try:
        return await get("/status")
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"clientgen error: {e}")

import os
import httpx

CLIENTGEN_URL = os.getenv("CLIENTGEN_URL", "http://clientgen:8000").rstrip("/")

async def post(path: str, payload: dict | None = None) -> dict:
    async with httpx.AsyncClient(timeout=5.0) as client:
        r = await client.post(f"{CLIENTGEN_URL}{path}", json=payload)
        r.raise_for_status()
        return r.json()

async def get(path: str) -> dict:
    async with httpx.AsyncClient(timeout=5.0) as client:
        r = await client.get(f"{CLIENTGEN_URL}{path}")
        r.raise_for_status()
        return r.json()

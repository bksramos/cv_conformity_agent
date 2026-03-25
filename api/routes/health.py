from __future__ import annotations
import httpx
import redis.asyncio as aioredis
from fastapi import APIRouter
from sqlalchemy import text

from api.schemas import HealthOut
from config.settings import settings
from database.connection import AsyncSessionLocal

router = APIRouter(tags=["Health"])


@router.get("/health", response_model=HealthOut)
async def health_check():
    services = {}

    # PostgreSQL
    try:
        async with AsyncSessionLocal() as s:
            await s.execute(text("SELECT 1"))
        services["postgres"] = "ok"
    except Exception as e:
        services["postgres"] = f"error: {e}"

    # Redis
    try:
        r = aioredis.from_url(settings.redis_url)
        await r.ping()
        await r.aclose()
        services["redis"] = "ok"
    except Exception as e:
        services["redis"] = f"error: {e}"

    # Ollama
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{settings.ollama_base_url}/api/tags")
            services["ollama"] = "ok" if resp.status_code == 200 else f"http {resp.status_code}"
    except Exception as e:
        services["ollama"] = f"error: {e}"

    # ChromaDB
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(
                f"http://{settings.chroma_host}:{settings.chroma_port}/api/v2/heartbeat"
            )
            services["chromadb"] = "ok" if resp.status_code == 200 else f"http {resp.status_code}"
    except Exception as e:
        services["chromadb"] = f"error: {e}"

    all_ok = all(v == "ok" for v in services.values())
    return HealthOut(
        status="healthy" if all_ok else "degraded",
        services=services,
    )


"""Liveness/readiness endpoints. No authentication — used by Compose/orchestrator healthchecks."""

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from revenueflowai.db import get_session
from revenueflowai.observability import registry

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}


@router.get("/metrics", response_class=PlainTextResponse)
async def metrics() -> str:
    return registry.render()


@router.get("/readyz")
async def readyz(session: AsyncSession = Depends(get_session)) -> dict:
    await session.execute(text("SELECT 1"))
    return {"status": "ready", "database": "connected"}

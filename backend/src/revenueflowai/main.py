"""FastAPI application entrypoint."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from revenueflowai.api.health import router as health_router
from revenueflowai.api.imports import router as imports_router
from revenueflowai.config import get_settings
from revenueflowai.storage.s3_store import S3CompatibleObjectStore

settings = get_settings()
log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    store = S3CompatibleObjectStore()
    for bucket in (settings.s3_bucket_raw_imports, settings.s3_bucket_exports):
        try:
            await store.ensure_bucket(bucket)
        except Exception:
            log.exception("Failed to ensure bucket %r exists on startup", bucket)
    yield


app = FastAPI(
    title="RevenueFlow AI",
    description="CSV-first Order-to-Cash Exception Intelligence API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(imports_router)

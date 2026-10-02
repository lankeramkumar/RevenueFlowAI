"""FastAPI application entrypoint."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from revenueflowai.api.health import router as health_router
from revenueflowai.config import get_settings

settings = get_settings()

app = FastAPI(
    title="RevenueFlow AI",
    description="CSV-first Order-to-Cash Exception Intelligence API",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)

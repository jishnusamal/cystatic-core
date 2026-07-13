"""FastAPI application for Cystatic runtime."""

from __future__ import annotations

from fastapi import FastAPI
from typing import Any
from fastapi.middleware.cors import CORSMiddleware

from api.routes.github import router as github_router
from api.routes.health import router as health_router
from api.settings import get_settings

settings = get_settings()

app = FastAPI(
    title="Cystatic API",
    description="Static analysis and change impact detection API",
    version=settings.APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict to specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Include routers
app.include_router(health_router)
app.include_router(github_router)


@app.get("/")
async def root() -> dict[str, str]:
    """Root endpoint."""
    return {
        "name": "Cystatic API",
        "version": settings.APP_VERSION,
        "status": "running",
    }


@app.get("/v1")
async def v1_root() -> dict[str, Any]:
    """V1 API root."""
    return {
        "version": "1.0",
        "endpoints": {
            "health": "/health",
            "github_webhook": "/webhooks/github",
            "analyze": "/v1/analyze",
        },
    }

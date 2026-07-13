"""Health check endpoint."""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from api.settings import get_settings

router = APIRouter(tags=["health"])

# Track application start time
_start_time: float = time.time()


@router.get("/health")
async def health_check() -> JSONResponse:
    """
    Health check endpoint.
    
    Returns application status, version, and uptime.
    """
    settings = get_settings()
    uptime = time.time() - _start_time
    
    return JSONResponse(
        content={
            "status": "healthy",
            "version": settings.APP_VERSION,
            "uptime_seconds": round(uptime, 2),
            "environment": settings.APP_ENV,
        }
    )


@router.get("/ready")
async def readiness_check() -> JSONResponse:
    """
    Readiness check endpoint.
    
    Checks if the application is ready to serve requests.
    """
    # In production, check dependencies here (database, cache, etc.)
    return JSONResponse(
        content={
            "status": "ready",
            "checks": {
                "compiler": "ok",
                "renderers": "ok",
            },
        }
    )
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
    
    Returns the current health status of the application including version,
    uptime, and environment information.
    
    Returns:
        JSONResponse: Application health status with the following fields:
            - status (str): Always "healthy" if the application is running
            - version (str): Application version from settings
            - uptime_seconds (float): Time since application start in seconds
            - environment (str): Current environment (e.g., "development", "production")
    
    Example Response:
        {
            "status": "healthy",
            "version": "1.0.0",
            "uptime_seconds": 123.45,
            "environment": "development"
        }
    
    Status Codes:
        200: Application is healthy and running
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
    
    Checks if the application is ready to serve requests by verifying
    that all required dependencies and services are available.
    
    Returns:
        JSONResponse: Readiness status with component checks:
            - status (str): "ready" if all checks pass
            - checks (dict): Status of individual components:
                - compiler (str): Status of the compiler component ("ok")
                - renderers (str): Status of the renderers component ("ok")
    
    Example Response:
        {
            "status": "ready",
            "checks": {
                "compiler": "ok",
                "renderers": "ok"
            }
        }
    
    Status Codes:
        200: Application is ready to serve requests
    
    Note:
        In production, this endpoint should check actual dependencies
        such as database connections, cache availability, etc.
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
"""FastAPI application for Cystatic runtime."""

from __future__ import annotations

from fastapi import FastAPI
from typing import Any
from fastapi.middleware.cors import CORSMiddleware

from integrations.github.routes import router as github_router
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
    """
    Root endpoint for the Cystatic API.
    
    Returns basic API information including name, version, and status.
    
    Returns:
        dict[str, str]: API information containing:
            - name (str): API name ("Factor API")
            - version (str): Current API version
            - status (str): Current API status (always "running" if accessible)
    
    Example Response:
        {
            "name": "Factor API",
            "version": "1.0.0",
            "status": "running"
        }
    
    Status Codes:
        200: API is running and accessible
    """
    return {
        "name": "Factor API",
        "version": settings.APP_VERSION,
        "status": "running",
    }


@app.get("/v1")
async def v1_root() -> dict[str, Any]:
    """
    V1 API root endpoint.
    
    Returns information about the V1 API version and available endpoints.
    
    Returns:
        dict[str, Any]: V1 API information containing:
            - version (str): API version ("1.0")
            - endpoints (dict): Available endpoints and their paths:
                - health (str): Health check endpoint path
                - github_webhook (str): GitHub webhook endpoint path
                - analyze (str): Repository analysis endpoint path
    
    Example Response:
        {
            "version": "1.0",
            "endpoints": {
                "health": "/health",
                "github_webhook": "/webhooks/github",
                "analyze": "/v1/analyze"
            }
        }
    
    Status Codes:
        200: V1 API information retrieved successfully
    """
    return {
        "version": "1.0",
        "endpoints": {
            "health": "/health",
            "github_webhook": "/webhooks/github",
            "analyze": "/v1/analyze",
        },
    }

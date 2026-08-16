"""FastAPI application for Factor runtime."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from api.routes.github import router as github_router
from api.routes.health import router as health_router
from core.config import get_settings

settings = get_settings()

app = FastAPI(
    title="Factor API",
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


@app.middleware("http")
async def memory_logging_middleware(request: Request, call_next) -> Any:
    """Middleware to track process memory metrics for every request."""
    import os
    import time
    import uuid
    import psutil
    from core.logging import pipeline_logger

    path = request.url.path
    if (
        path in {"/", "/health", "/ready", "/docs", "/redoc", "/openapi.json"}
        or path.startswith(("/docs", "/redoc"))
    ):
        return await call_next(request)

    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())[:8]
    process = psutil.Process(os.getpid())

    start_rss = process.memory_info().rss / (1024 * 1024)
    start_time = time.perf_counter()

    pipeline_logger.log_pipeline(
        f"[MEMORY][request={request_id}] {request.method} {path} - Starting | RSS={start_rss:.1f} MB",
        to_terminal=True,
    )

    try:
        response = await call_next(request)
        end_rss = process.memory_info().rss / (1024 * 1024)
        duration = time.perf_counter() - start_time
        delta_rss = end_rss - start_rss

        pipeline_logger.log_pipeline(
            f"[MEMORY][request={request_id}] {request.method} {path} - Finished | "
            f"Status={response.status_code} | "
            f"Start RSS={start_rss:.1f} MB | End RSS={end_rss:.1f} MB | "
            f"Δ={'+' if delta_rss >= 0 else ''}{delta_rss:.1f} MB | "
            f"Duration={duration:.2f}s",
            to_terminal=True,
        )
        return response
    except Exception as e:
        end_rss = process.memory_info().rss / (1024 * 1024)
        duration = time.perf_counter() - start_time
        delta_rss = end_rss - start_rss

        pipeline_logger.log_pipeline(
            f"[MEMORY][request={request_id}] {request.method} {path} - Failed | "
            f"Error={type(e).__name__} | "
            f"Start RSS={start_rss:.1f} MB | End RSS={end_rss:.1f} MB | "
            f"Δ={'+' if delta_rss >= 0 else ''}{delta_rss:.1f} MB | "
            f"Duration={duration:.2f}s",
            to_terminal=True,
        )
        raise e


# Include routers
app.include_router(health_router)
app.include_router(github_router)


@app.get("/")
async def root() -> dict[str, str]:
    """Root endpoint for the Factor API.

    Returns basic API information including name, version, and status.
    """
    return {
        "name": "Factor API",
        "version": settings.APP_VERSION,
        "status": "running",
    }


@app.get("/v1")
async def v1_root() -> dict[str, Any]:
    """V1 API root endpoint.

    Returns information about the V1 API version and available endpoints.
    """
    return {
        "version": "1.0",
        "endpoints": {
            "health": "/health",
            "github_webhook": "/github",
            "analyze": "/v1/analyze",
        },
    }

"""Analysis routes stub.

TODO: Implement analysis management endpoints (list runs, get results, etc.)
Note: The /v1/analyze endpoint lives in api/routes/github.py for now.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/v1/analyses", tags=["analysis"])


# TODO: Add analysis management endpoints
# @router.get("/{analysis_id}")
# async def get_analysis(analysis_id: str) -> dict:
#     """Get analysis result by ID."""
#     ...
#
# @router.get("/")
# async def list_analyses(repo: str | None = None) -> list:
#     """List recent analyses, optionally filtered by repo."""
#     ...

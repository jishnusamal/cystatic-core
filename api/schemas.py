"""Request and response models for the API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = "ok"


class AnalyzeRequest(BaseModel):
    """Minimal payload to trigger an analysis run."""

    repo_url: str = Field(..., description="Clone URL or web URL for the repository")
    ref: str = Field(default="main", description="Branch, tag, or commit")
    changed_paths: list[str] = Field(default_factory=list, description="Paths changed in the PR")


class BlastRadiusResponse(BaseModel):
    affected_files: list[str]
    impact_score: float
    risk_level: str

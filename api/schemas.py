"""Request and response models for the API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = "ok"


class AnalyzeRequest(BaseModel):
    """Minimal payload to trigger an analysis run."""
    repo: str = Field(..., description="Clone URL or web URL for the repository")
    pr_number: int = Field(default=0, description="Pull request number")
    diff_url: str = Field(..., description="URL for the diff of the PR")
    diff: str = Field(..., description="The diff content")



class BlastRadiusResponse(BaseModel):
    affected_files: list[str]
    impact_score: float
    risk_level: str

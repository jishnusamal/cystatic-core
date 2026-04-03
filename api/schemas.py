"""Request and response models for the API."""

from __future__ import annotations
from pydantic import BaseModel, Field

class HealthResponse(BaseModel):
    status: str = "ok"
    

class AnalyzeRequest(BaseModel):
    """Minimal payload to trigger an analysis run."""
    repo: str = Field(..., description="Full repo name in owner/repo format")
    pr_number: int = Field(..., description="Pull request number")
    
class BlastRadiusResponse(BaseModel):
    affected_files: list[str]
    impact_score: float
    risk_level: str

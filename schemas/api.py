"""Request and response models for the API."""

from __future__ import annotations
from pydantic import BaseModel, Field

class AnalyzeRequest(BaseModel):
    """Minimal payload to trigger an analysis run."""
    repo: str = Field(..., description="Full repo name in owner/repo format")
    pr_number: int = Field(..., description="Pull request number")
    
class AnalyzeDiff(AnalyzeRequest):
    """Payload for diff analysis."""
    repo: str = Field(default="usefactorhq/usefactor", description="Full repo name in owner/repo format")
    pr_number: int = Field(default=1, description="Pull request number")
    diff: str = Field(..., description="Unified diff string to analyze")
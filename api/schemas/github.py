"""API schemas for GitHub-related endpoints."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class WebhookResponse(BaseModel):
    """Response for webhook endpoints."""
    
    status: str = "accepted"
    message: str | None = None


class PRWebhookPayload(BaseModel):
    """GitHub pull request webhook payload."""
    
    action: str
    repository: dict[str, Any]
    pull_request: dict[str, Any]
    installation: dict[str, Any] | None = None


class AnalysisRequest(BaseModel):
    """Request to analyze a repository."""
    
    repository: str = Field(..., description="Repository identifier (e.g., 'owner/repo')")
    base_sha: str | None = Field(None, description="Base commit SHA")
    head_sha: str | None = Field(None, description="Head commit SHA")
    pr_number: int | None = Field(None, description="Pull request number")
    diff_data: dict[str, Any] | None = Field(None, description="Raw diff data")


class AnalysisResponse(BaseModel):
    """Response from analysis endpoint."""
    
    repository: str
    language: str
    change_summary: dict[str, Any]
    behavior_summary: dict[str, Any]
    operational_summary: dict[str, Any]
    timing: dict[str, float]
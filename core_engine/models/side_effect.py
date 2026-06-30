"""
SideEffect — a first-class model for side effects detected by analyzers.

Replaces the generic ``dict[str, Any]`` placeholder in EvidenceBundle.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SideEffect(BaseModel):
    """A side effect introduced or affected by a change.

    Attributes:
        description: Human-readable description of the side effect.
        symbol: The symbol responsible for the side effect.
        effect_type: Category of side effect (e.g. "write", "network_call", "file_io").
        confidence: Confidence this side effect is real (0.0-1.0).
        metadata: Additional structured data.
    """
    description: str = Field(..., min_length=1)
    symbol: str = Field(..., min_length=1)
    effect_type: str = Field(default="unknown")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)
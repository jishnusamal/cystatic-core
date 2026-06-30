"""
ImpactEvidence — primary architectural primitive.

Every deterministic analyzer emits ImpactEvidence.

ImpactEvidence represents facts — not predictions.

Attributes:
    source: The originating entity (symbol, service, endpoint, etc.).
    target: The affected entity.
    evidence_type: The type of connection between source and target.
    confidence: Confidence in this evidence (0.0–1.0).
    explanation: Human-readable explanation of the connection.
    metadata: Additional structured data about this evidence.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from .enums import EvidenceType
from .entity_ref import EntityRef


class ImpactEvidence(BaseModel):
    """A deterministic fact connecting two entities.

    This is the primary output of all deterministic analyzers.
    It represents observed structural or behavioral relationships,
    not probabilistic inferences.
    """
    source: EntityRef
    target: EntityRef

    evidence_type: EvidenceType

    confidence: float = Field(ge=0.0, le=1.0)

    explanation: str = Field(..., min_length=1)

    metadata: dict[str, Any] = Field(default_factory=dict)
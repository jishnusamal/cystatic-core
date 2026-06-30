"""
BusinessObject — a first-class model for business objects referenced by a change.

Replaces the generic ``dict[str, Any]`` placeholder in EvidenceBundle.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class BusinessObject(BaseModel):
    """A business object referenced by a change.

    Attributes:
        name: Name of the business object (e.g. "Invoice", "Order", "Payment").
        domain: Business domain this object belongs to.
        description: Human-readable description of the business object.
    """
    name: str = Field(..., min_length=1)
    domain: str | None = None
    description: str = Field(default="")
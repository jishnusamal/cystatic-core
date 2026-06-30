"""
RiskAnchor — represents changes known to increase downstream uncertainty.

Responsibilities:
  - risk classification
  - business-domain tagging
  - business-object tagging
  - operational characteristics
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from .enums import RiskAnchorType


class RiskAnchor(BaseModel):
    """A change that increases downstream uncertainty.

    Attributes:
        anchor_type: The category of risk (money_flow, transaction_boundary, etc.).
        symbol: The symbol associated with this risk.
        confidence: Confidence that this is a genuine risk anchor (0.0–1.0).
        business_domain: Business domain this anchor belongs to.
        business_object: Specific business object affected (e.g. "Invoice", "Order").
        characteristics: Operational characteristics of this anchor.
        explanation: Human-readable explanation of why this is a risk anchor.
    """
    anchor_type: RiskAnchorType

    symbol: str = Field(..., min_length=1)

    confidence: float = Field(ge=0.0, le=1.0)

    business_domain: str | None = None

    business_object: str | None = None

    characteristics: list[str] = Field(default_factory=list)

    explanation: str = Field(..., min_length=1)
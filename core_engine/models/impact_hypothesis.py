"""
ImpactHypothesis — represents an inferred downstream behavioral consequence.

ImpactHypotheses are probabilistic.
Evidence (ImpactEvidence) remains deterministic.

Example:
    "Tax calculation changes may affect invoice totals."
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from .impact_evidence import ImpactEvidence


class ImpactHypothesis(BaseModel):
    """An inferred downstream behavioral consequence.
    
    This is a probabilistic inference built on top of deterministic
    ImpactEvidence. It represents what *might* happen as a result
    of the change, not what is guaranteed to happen.
    
    Attributes:
        hypothesis: A statement of the inferred consequence.
        confidence: Confidence in this hypothesis (0.0–1.0).
        supporting_evidence: Deterministic evidence supporting this hypothesis.
        assumptions: Assumptions underlying this hypothesis.
        affected_systems: Systems that may be affected by this consequence.
        source_symbol: Source symbol of the impact.
        target_symbol: Target symbol of the impact.
        impact_type: Type of impact (e.g., financial_impact, security_impact).
        description: Detailed description of the impact.
        evidence_summary: Summary of supporting evidence.
        affected_business_objects: Business objects affected by this impact.
        affected_domains: Business domains affected by this impact.
    """
    hypothesis: str = Field(..., min_length=1)
    
    confidence: float = Field(ge=0.0, le=1.0)
    
    supporting_evidence: list[ImpactEvidence] = Field(default_factory=list)
    
    assumptions: list[str] = Field(default_factory=list)
    
    affected_systems: list[str] = Field(default_factory=list)
    
    source_symbol: str = Field(default="")
    
    target_symbol: str = Field(default="")
    
    impact_type: str = Field(default="unknown_impact")
    
    description: str = Field(default="")
    
    evidence_summary: str = Field(default="")
    
    affected_business_objects: list[str] = Field(default_factory=list)
    
    affected_domains: list[str] = Field(default_factory=list)

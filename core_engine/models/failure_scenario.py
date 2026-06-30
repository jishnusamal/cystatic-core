"""
FailureScenario — represents plausible production failure narratives.

Example chain:
    Tax metadata malformed
    ↓
    Incorrect invoice totals
    ↓
    Customers charged incorrect amounts
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from .impact_hypothesis import ImpactHypothesis


class FailureScenario(BaseModel):
    """A plausible production failure narrative.
    
    This is the presentation layer — user-facing narratives built on
    deterministic evidence and probabilistic hypotheses.
    
    Attributes:
        title: Short title for the failure scenario.
        narrative: Detailed narrative of how the failure propagates.
        confidence: Confidence this scenario is realistic (0.0–1.0).
        supporting_hypotheses: Probabilistic hypotheses supporting this scenario.
        affected_domains: Business domains affected by this failure.
        operational_impact: Description of the operational impact.
        impact_type: Type of impact (e.g., financial_impact, security_impact).
        source_symbol: Source symbol where the failure originates.
        target_symbol: Target symbol that is affected.
        description: Detailed description of the failure scenario.
        reasoning: Reasoning behind the failure scenario.
        affected_business_objects: Business objects affected by this failure.
        silent_failure: Whether this is likely a silent failure.
        first_observable_signal: First observable signal of this failure.
        merge_risk_level: Risk level for merging (HIGH, MEDIUM, LOW).
        ci_would_catch: Whether CI would likely catch this failure.
        causal_chain: Description of the causal chain.
        failure_class: Classification of the failure type.
    """
    title: str = Field(..., min_length=1)
    
    narrative: str = Field(..., min_length=1)
    
    confidence: float = Field(ge=0.0, le=1.0)
    
    supporting_hypotheses: list[ImpactHypothesis] = Field(default_factory=list)
    
    affected_domains: list[str] = Field(default_factory=list)
    
    operational_impact: str = Field(..., min_length=1)
    
    impact_type: str = Field(default="unknown_impact")
    
    source_symbol: str = Field(default="")
    
    target_symbol: str = Field(default="")
    
    description: str = Field(default="")
    
    reasoning: str = Field(default="")
    
    affected_business_objects: list[str] = Field(default_factory=list)
    
    silent_failure: bool = Field(default=True)
    
    first_observable_signal: str = Field(default="unknown")
    
    merge_risk_level: str = Field(default="MEDIUM")
    
    ci_would_catch: bool = Field(default=False)
    
    causal_chain: str = Field(default="")
    
    failure_class: str = Field(default="")

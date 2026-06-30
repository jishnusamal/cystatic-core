"""
EvidenceBundle — aggregates evidence from all analyzers into a single
semantic representation consumed by downstream reasoning.

This replaces propagation output as the primary reasoning input.

Contains:
  - ChangedSymbols
  - RiskAnchors
  - ImpactEvidence
  - SideEffects
  - Constraints
  - Domains
  - Business Objects
  - Confidence metadata
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from .changed_symbol import ChangedSymbol
from .risk_anchor import RiskAnchor
from .impact_evidence import ImpactEvidence
from .side_effect import SideEffect
from .constraint import Constraint
from .business_object import BusinessObject


class EvidenceBundle(BaseModel):
    """Aggregated evidence from all deterministic analyzers.

    This is the single semantic representation consumed by downstream
    reasoning (ImpactHypothesis generation, FailureScenario construction).

    Attributes:
        changed_symbols: All symbols modified by the change.
        risk_anchors: Changes known to increase downstream uncertainty.
        impact_evidence: Deterministic facts connecting entities.
        side_effects: Side effects introduced or affected by the change.
        constraints: Constraints that apply to the change.
        business_objects: Business objects referenced by the change.
        domains: Business domains touched by the change.
        confidence: Overall confidence in this evidence bundle (0.0–1.0).
    """
    changed_symbols: list[ChangedSymbol] = Field(default_factory=list)

    risk_anchors: list[RiskAnchor] = Field(default_factory=list)

    impact_evidence: list[ImpactEvidence] = Field(default_factory=list)

    side_effects: list[SideEffect] = Field(default_factory=list)

    constraints: list[Constraint] = Field(default_factory=list)

    business_objects: list[BusinessObject] = Field(default_factory=list)

    domains: list[str] = Field(default_factory=list)

    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
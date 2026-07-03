"""
Core domain models for cystatic.

Architectural layers:
  1. Facts (deterministic) — ChangedSymbol, RiskAnchor, ImpactEvidence, EvidenceBundle
  2. Probabilistic inference — ImpactHypothesis
  3. Presentation / narrative — FailureScenario

Enums, EntityRef, and shared value objects live alongside their consumers.
"""
from __future__ import annotations

from .enums import (
    SymbolKind,
    RiskAnchorType,
    EvidenceType,
)
from .entity_ref import EntityRef
from .changed_symbol import ChangedSymbol
from .risk_anchor import RiskAnchor
from .impact_evidence import ImpactEvidence
from .side_effect import SideEffect
from .constraint import Constraint
from .business_object import BusinessObject
from .evidence_bundle import EvidenceBundle
from .impact_hypothesis import ImpactHypothesis
from .failure_scenario import FailureScenario
from .normalized_facts import (
    ArchitecturalFact,
    CanonicalRisk,
    ProductionInvariant,
    ValidationGap,
    ReviewerQuestion,
    MergeFact,
    NormalizedReviewFacts,
)

__all__ = [
    # Enums
    "SymbolKind",
    "RiskAnchorType",
    "EvidenceType",
    # Value objects
    "EntityRef",
    # Deterministic facts
    "ChangedSymbol",
    "RiskAnchor",
    "ImpactEvidence",
    "SideEffect",
    "Constraint",
    "BusinessObject",
    "EvidenceBundle",
    # Probabilistic inference
    "ImpactHypothesis",
    # Presentation
    "FailureScenario",
    # Normalized review facts
    "ArchitecturalFact",
    "CanonicalRisk",
    "ProductionInvariant",
    "ValidationGap",
    "ReviewerQuestion",
    "MergeFact",
    "NormalizedReviewFacts",
]

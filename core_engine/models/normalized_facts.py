"""
Normalized review facts — reviewer-ready semantic representation.

This module defines the output models for the Evidence Normalization Layer.
These models represent engineering facts, not internal implementation artifacts.
"""
from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class ArchitecturalFact(BaseModel):
    """A deterministic architectural observation.
    
    Attributes:
        title: Short title for the fact.
        description: Detailed description of the architectural observation.
        symbols: Symbols involved in this fact.
        domains: Domains affected by this fact.
        confidence: Confidence in this fact (0.0–1.0).
        supporting_evidence: Evidence supporting this fact.
    """
    title: str = Field(..., min_length=1)
    description: str = Field(default="")
    symbols: list[str] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    supporting_evidence: list[str] = Field(default_factory=list)


class CanonicalRisk(BaseModel):
    """A canonical risk representation.
    
    Attributes:
        title: Short title for the risk.
        affected_symbols: Symbols affected by this risk.
        affected_domains: Domains affected by this risk.
        production_invariant: The production invariant that may be violated.
        confidence: Confidence in this risk (0.0–1.0).
        supporting_evidence: Evidence supporting this risk.
    """
    title: str = Field(..., min_length=1)
    affected_symbols: list[str] = Field(default_factory=list)
    affected_domains: list[str] = Field(default_factory=list)
    production_invariant: str = Field(default="")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    supporting_evidence: list[str] = Field(default_factory=list)


class ProductionInvariant(BaseModel):
    """A production invariant that must be maintained.
    
    Attributes:
        statement: The invariant statement.
        business_objects: Business objects involved in this invariant.
        symbols: Symbols that enforce or relate to this invariant.
        domains: Domains affected by this invariant.
        confidence: Confidence that this invariant exists (0.0–1.0).
    """
    statement: str = Field(..., min_length=1)
    business_objects: list[str] = Field(default_factory=list)
    symbols: list[str] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class ValidationGap(BaseModel):
    """A gap in validation coverage.
    
    Attributes:
        description: Description of the validation gap.
        invariant: The production invariant that lacks validation.
        existing_validation: What validation currently exists.
        missing_validation: What validation is missing.
        affected_symbols: Symbols affected by this gap.
        affected_domains: Domains affected by this gap.
        confidence: Confidence in this gap (0.0–1.0).
    """
    description: str = Field(..., min_length=1)
    invariant: str = Field(default="")
    existing_validation: str = Field(default="")
    missing_validation: str = Field(default="")
    affected_symbols: list[str] = Field(default_factory=list)
    affected_domains: list[str] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class ReviewerQuestion(BaseModel):
    """A question for the reviewer.
    
    Attributes:
        question: The question text.
        context: Context for why this question is being asked.
        related_symbols: Symbols related to this question.
        related_domains: Domains related to this question.
        priority: Priority level (high, medium, low).
    """
    question: str = Field(..., min_length=1)
    context: str = Field(default="")
    related_symbols: list[str] = Field(default_factory=list)
    related_domains: list[str] = Field(default_factory=list)
    priority: str = Field(default="medium")  # high, medium, low


class MergeFact(BaseModel):
    """An objective merge fact.
    
    Attributes:
        fact: The merge fact statement.
        category: Category of the fact (e.g., validation, coverage, risk).
        supporting_evidence: Evidence supporting this fact.
        confidence: Confidence in this fact (0.0–1.0).
    """
    fact: str = Field(..., min_length=1)
    category: str = Field(default="general")
    supporting_evidence: list[str] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class NormalizedReviewFacts(BaseModel):
    """Complete set of reviewer-ready facts.
    
    This is the output of the Evidence Normalization Layer and the input
    to the ReviewPipeline. It contains only deterministic, structured facts.
    
    Attributes:
        verdict_input: Input for verdict determination.
        architectural_facts: Architectural observations.
        canonical_risks: Canonical risk representations.
        production_invariants: Production invariants.
        validation_gaps: Validation coverage gaps.
        reviewer_questions: Questions for the reviewer.
        merge_facts: Objective merge facts.
        compression_stats: Compression statistics from inference.
        overall_confidence: Overall confidence in the analysis (0.0–1.0).
    """
    verdict_input: dict[str, Any] = Field(default_factory=dict)
    architectural_facts: list[ArchitecturalFact] = Field(default_factory=list)
    canonical_risks: list[CanonicalRisk] = Field(default_factory=list)
    production_invariants: list[ProductionInvariant] = Field(default_factory=list)
    validation_gaps: list[ValidationGap] = Field(default_factory=list)
    reviewer_questions: list[ReviewerQuestion] = Field(default_factory=list)
    merge_facts: list[MergeFact] = Field(default_factory=list)
    compression_stats: dict[str, Any] = Field(default_factory=dict)
    overall_confidence: float = Field(default=1.0, ge=0.0, le=1.0)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return self.model_dump()
"""
Base Analyzer Interface

All evidence analyzers implement this interface.
Analyzers are independent - no analyzer depends on another.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any
from pydantic import BaseModel, Field


class AnalyzerOutput(BaseModel):
    """Structured output from an evidence analyzer.
    
    Attributes:
        changed_symbols: Symbols modified by this analyzer's scope.
        risk_anchors: Risk anchors identified by this analyzer.
        impact_evidence: Deterministic evidence facts produced by this analyzer.
        side_effects: Side effects detected by this analyzer.
        constraints: Constraints extracted by this analyzer.
        business_objects: Business objects referenced by this analyzer.
        metadata: Additional analyzer-specific metadata.
    """
    changed_symbols: list[dict[str, Any]] = Field(default_factory=list)
    risk_anchors: list[dict[str, Any]] = Field(default_factory=list)
    impact_evidence: list[dict[str, Any]] = Field(default_factory=list)
    side_effects: list[dict[str, Any]] = Field(default_factory=list)
    constraints: list[dict[str, Any]] = Field(default_factory=list)
    business_objects: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvidenceAnalyzer(ABC):
    """Base interface for all evidence analyzers.
    
    Each analyzer:
    - Is independent (no dependencies on other analyzers)
    - Operates on AnalysisContext only
    - Produces deterministic facts (AnalyzerOutput)
    - Never creates hypotheses or predictions
    """
    
    @abstractmethod
    def analyze(self, context: AnalysisContext) -> AnalyzerOutput:
        """Analyze the context and produce deterministic evidence.
        
        Args:
            context: AnalysisContext containing all PR/diff information.
            
        Returns:
            AnalyzerOutput with all evidence extracted by this analyzer.
        """
        pass


# Import here to avoid circular dependency
from core_engine.analysers.analysis_context import AnalysisContext
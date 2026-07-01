"""
Evidence Registry — centralized API for collecting and aggregating evidence.

This replaces the pattern where each analyzer independently appends to lists.
The registry:
- Deduplicates identical evidence
- Merges confidences from multiple analyzers
- Tracks provenance
- Produces the final EvidenceBundle
"""
from __future__ import annotations

from typing import Any
from collections import defaultdict
from pydantic import BaseModel, Field

from .base import AnalyzerOutput
from .analysis_context import AnalysisContext
from core_engine.models.evidence_bundle import EvidenceBundle
from core_engine.models.impact_evidence import ImpactEvidence
from core_engine.models.changed_symbol import ChangedSymbol
from core_engine.models.risk_anchor import RiskAnchor
from core_engine.models.side_effect import SideEffect
from core_engine.models.constraint import Constraint
from core_engine.models.business_object import BusinessObject
from core_engine.models.enums import EvidenceType


class EvidenceEntry(BaseModel):
    """Single evidence entry in the registry."""
    source: str
    target: str
    evidence_type: EvidenceType
    confidence: float = Field(ge=0.0, le=1.0)
    explanation: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    analyzer: str = "unknown"
    
    def to_impact_evidence(self) -> ImpactEvidence:
        """Convert to ImpactEvidence model."""
        from core_engine.models.entity_ref import EntityRef
        return ImpactEvidence(
            source=EntityRef(kind="symbol", id=self.source, name=self.source.split(".")[-1] if self.source else ""),
            target=EntityRef(kind="symbol", id=self.target, name=self.target.split(".")[-1] if self.target else ""),
            evidence_type=self.evidence_type,
            confidence=self.confidence,
            explanation=self.explanation,
            metadata=self.metadata,
        )


class EvidenceRegistry:
    """Centralized registry for collecting and aggregating evidence.
    
    This registry:
    - Provides a unified API for analyzers to add evidence
    - Deduplicates evidence based on (source, target, evidence_type)
    - Merges confidences when the same evidence is found by multiple analyzers
    - Tracks which analyzer produced each piece of evidence
    - Produces the final EvidenceBundle with aggregated confidence
    
    Usage:
        registry = EvidenceRegistry()
        registry.add_evidence(
            source="TaxCalculator",
            target="Invoice",
            evidence_type=EvidenceType.SHARED_BUSINESS_OBJECT,
            confidence=0.7,
            explanation="Both reference Invoice",
            analyzer="BusinessObjectAnalyzer"
        )
        
        # Later, produce the bundle
        bundle = registry.build_bundle()
    """
    
    def __init__(self):
        # Key: (source, target, evidence_type) -> EvidenceEntry
        self._evidence: dict[tuple[str, str, str], EvidenceEntry] = {}
        
        # Other collections
        self._changed_symbols: list[ChangedSymbol] = []
        self._risk_anchors: list[RiskAnchor] = []
        self._side_effects: list[SideEffect] = []
        self._constraints: list[Constraint] = []
        self._business_objects: list[BusinessObject] = []
        
        # Track provenance
        self._analyzer_contributions: dict[str, int] = defaultdict(int)
    
    def add_evidence(
        self,
        source: str,
        target: str,
        evidence_type: EvidenceType | str,
        confidence: float = 0.5,
        explanation: str = "",
        metadata: dict[str, Any] | None = None,
        analyzer: str = "unknown",
    ) -> None:
        """Add evidence to the registry.
        
        If the same (source, target, evidence_type) already exists,
        the confidences are merged using weighted averaging.
        
        Args:
            source: Source entity (symbol, service, domain, etc.)
            target: Target entity
            evidence_type: Type of evidence/relationship
            confidence: Confidence in this evidence (0.0-1.0)
            explanation: Human-readable explanation
            metadata: Additional structured data
            analyzer: Name of the analyzer producing this evidence
        """
        if isinstance(evidence_type, str):
            evidence_type = EvidenceType(evidence_type)
        
        key = (source, target, evidence_type.value)
        
        if key in self._evidence:
            # Merge with existing evidence - weighted average based on confidence
            existing = self._evidence[key]
            total_weight = existing.confidence + confidence
            if total_weight > 0:
                merged_confidence = (
                    (existing.confidence * existing.confidence + confidence * confidence) 
                    / total_weight
                )
            else:
                merged_confidence = 0.0
            
            existing.confidence = min(merged_confidence, 1.0)
            existing.explanation = f"{existing.explanation}; {explanation}".strip("; ")
            existing.metadata.update(metadata or {})
            existing.analyzer = f"{existing.analyzer}, {analyzer}"
        else:
            self._evidence[key] = EvidenceEntry(
                source=source,
                target=target,
                evidence_type=evidence_type,
                confidence=confidence,
                explanation=explanation,
                metadata=metadata or {},
                analyzer=analyzer,
            )
        
        self._analyzer_contributions[analyzer] += 1
    
    def add_changed_symbol(self, symbol: ChangedSymbol | dict[str, Any]) -> None:
        """Add a changed symbol."""
        if isinstance(symbol, dict):
            symbol = ChangedSymbol(**symbol)
        self._changed_symbols.append(symbol)
    
    def add_risk_anchor(self, anchor: RiskAnchor | dict[str, Any]) -> None:
        """Add a risk anchor."""
        if isinstance(anchor, dict):
            anchor = RiskAnchor(**anchor)
        self._risk_anchors.append(anchor)
    
    def add_side_effect(self, effect: SideEffect | dict[str, Any]) -> None:
        """Add a side effect."""
        if isinstance(effect, dict):
            effect = SideEffect(**effect)
        self._side_effects.append(effect)
    
    def add_constraint(self, constraint: Constraint | dict[str, Any]) -> None:
        """Add a constraint."""
        if isinstance(constraint, dict):
            constraint = Constraint(**constraint)
        self._constraints.append(constraint)
    
    def add_business_object(self, obj: BusinessObject | dict[str, Any]) -> None:
        """Add a business object."""
        if isinstance(obj, dict):
            obj = BusinessObject(**obj)
        self._business_objects.append(obj)
    
    def ingest_analyzer_output(self, output: AnalyzerOutput, analyzer_name: str) -> None:
        """Ingest all evidence from an analyzer output.
        
        This is the main integration point for analyzers.
        
        Args:
            output: AnalyzerOutput from an analyzer
            analyzer_name: Name of the analyzer (for provenance)
        """
        # Add changed symbols
        for cs in output.changed_symbols:
            self.add_changed_symbol(cs)
        
        # Add risk anchors
        for ra in output.risk_anchors:
            self.add_risk_anchor(ra)
        
        # Add impact evidence
        for ie in output.impact_evidence:
            if isinstance(ie, dict):
                source = ie.get("source_symbol", "")
                target = ie.get("target_symbol", "")
                evidence_type = ie.get("evidence_type", "symbol_reference")
                confidence = ie.get("confidence", 0.5)
                explanation = ie.get("explanation", "")
                metadata = ie.get("metadata", {})
            else:
                source = ie.source_symbol
                target = ie.target_symbol
                evidence_type = ie.evidence_type
                confidence = ie.confidence
                explanation = ie.explanation
                metadata = ie.metadata
            
            self.add_evidence(
                source=source,
                target=target,
                evidence_type=evidence_type,
                confidence=confidence,
                explanation=explanation,
                metadata=metadata,
                analyzer=analyzer_name,
            )
        
        # Add side effects
        for se in output.side_effects:
            self.add_side_effect(se)
        
        # Add constraints
        for c in output.constraints:
            self.add_constraint(c)
        
        # Add business objects
        for bo in output.business_objects:
            self.add_business_object(bo)
    
    def build_bundle(self) -> EvidenceBundle:
        """Build the final EvidenceBundle from all collected evidence.
        
        Returns:
            EvidenceBundle with all aggregated evidence
        """
        # Convert evidence entries to ImpactEvidence objects
        impact_evidence_list = [entry.to_impact_evidence() for entry in self._evidence.values()]
        
        # Calculate overall confidence based on evidence density
        overall_confidence = self._calculate_overall_confidence()
        
        # Extract domains from business objects
        domains = list(set(
            bo.domain if hasattr(bo, 'domain') else bo.get('domain', 'general')
            for bo in self._business_objects
        ))
        
        return EvidenceBundle(
            changed_symbols=self._changed_symbols,
            risk_anchors=self._risk_anchors,
            impact_evidence=impact_evidence_list,
            side_effects=self._side_effects,
            constraints=self._constraints,
            business_objects=self._business_objects,
            domains=domains,
            confidence=overall_confidence,
        )
    
    def _calculate_overall_confidence(self) -> float:
        """Calculate overall confidence in the evidence bundle.
        
        Based on:
        - Number of analyzers that contributed
        - Evidence density (evidence per analyzer)
        - Average confidence of all evidence
        
        Returns:
            Overall confidence score (0.0-1.0)
        """
        if not self._evidence:
            return 1.0  # No evidence = high confidence in "nothing to report"
        
        # Factor 1: Number of contributing analyzers (more = better)
        num_analyzers = len(self._analyzer_contributions)
        analyzer_score = min(num_analyzers / 5.0, 1.0)  # 5 analyzers = full score
        
        # Factor 2: Average evidence confidence
        avg_confidence = sum(e.confidence for e in self._evidence.values()) / len(self._evidence)
        
        # Factor 3: Evidence diversity (unique evidence types)
        unique_types = len(set(e.evidence_type for e in self._evidence.values()))
        diversity_score = min(unique_types / 10.0, 1.0)  # 10 types = full score
        
        # Weighted combination
        overall = (
            analyzer_score * 0.3 +
            avg_confidence * 0.5 +
            diversity_score * 0.2
        )
        
        return round(min(overall, 1.0), 3)
    
    def get_stats(self) -> dict[str, Any]:
        """Get statistics about the registry contents."""
        return {
            "total_evidence": len(self._evidence),
            "total_changed_symbols": len(self._changed_symbols),
            "total_risk_anchors": len(self._risk_anchors),
            "total_side_effects": len(self._side_effects),
            "total_constraints": len(self._constraints),
            "total_business_objects": len(self._business_objects),
            "analyzer_contributions": dict(self._analyzer_contributions),
            "evidence_types": list(set(e.evidence_type for e in self._evidence.values())),
        }
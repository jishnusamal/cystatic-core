"""
Analyzer Registry — owns execution of all evidence analyzers.

The orchestrator never calls analyzers directly.
The registry owns execution and aggregates results.
"""
from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field

from .base import EvidenceAnalyzer, AnalyzerOutput
from .analysis_context import AnalysisContext


class AnalyzerRegistry:
    """Registry that owns execution of all evidence analyzers.
    
    The orchestrator delegates to this registry rather than calling
    analyzers directly. This centralizes analyzer management and
    ensures consistent execution.
    
    Usage:
        registry = AnalyzerRegistry()
        registry.register(ChangedSymbolAnalyzer())
        registry.register(SideEffectAnalyzer())
        # ... register all analyzers
        
        bundle = registry.analyze_all(context)
    """
    
    def __init__(self):
        self._analyzers: list[EvidenceAnalyzer] = []
    
    def register(self, analyzer: EvidenceAnalyzer) -> None:
        """Register an analyzer with the registry.
        
        Args:
            analyzer: The analyzer to register.
        """
        self._analyzers.append(analyzer)
    
    def analyze_all(self, context: AnalysisContext) -> EvidenceBundle:
        """Execute all registered analyzers and aggregate results.
        
        Args:
            context: The analysis context to process.
            
        Returns:
            EvidenceBundle containing all evidence from all analyzers.
        """
        from core_engine.models.evidence_bundle import EvidenceBundle
        from core_engine.models.changed_symbol import ChangedSymbol
        from core_engine.models.risk_anchor import RiskAnchor
        from core_engine.models.impact_evidence import ImpactEvidence
        from core_engine.models.entity_ref import EntityRef
        from core_engine.models.side_effect import SideEffect
        from core_engine.models.constraint import Constraint
        from core_engine.models.business_object import BusinessObject
        
        # Aggregate outputs from all analyzers
        all_changed_symbols: list[ChangedSymbol] = []
        all_risk_anchors: list[RiskAnchor] = []
        all_impact_evidence: list[ImpactEvidence] = []
        all_side_effects: list[SideEffect] = []
        all_constraints: list[Constraint] = []
        all_business_objects: list[BusinessObject] = []
        
        for analyzer in self._analyzers:
            try:
                output = analyzer.analyze(context)
                
                # Convert and aggregate changed symbols
                for cs in output.changed_symbols:
                    if isinstance(cs, dict):
                        all_changed_symbols.append(ChangedSymbol(**cs))
                    else:
                        all_changed_symbols.append(cs)
                
                # Convert and aggregate risk anchors
                for ra in output.risk_anchors:
                    if isinstance(ra, dict):
                        all_risk_anchors.append(RiskAnchor(**ra))
                    else:
                        all_risk_anchors.append(ra)
                
                # Convert and aggregate impact evidence
                for ie in output.impact_evidence:
                    if isinstance(ie, dict):
                        all_impact_evidence.append(ImpactEvidence(**ie))
                    else:
                        all_impact_evidence.append(ie)
                
                # Convert and aggregate side effects
                for se in output.side_effects:
                    if isinstance(se, dict):
                        all_side_effects.append(SideEffect(**se))
                    else:
                        all_side_effects.append(se)
                
                # Convert and aggregate constraints
                for c in output.constraints:
                    if isinstance(c, dict):
                        all_constraints.append(Constraint(**c))
                    else:
                        all_constraints.append(c)
                
                # Convert and aggregate business objects
                for bo in output.business_objects:
                    if isinstance(bo, dict):
                        all_business_objects.append(BusinessObject(**bo))
                    else:
                        all_business_objects.append(bo)
            except Exception as e:
                # Log but don't fail - individual analyzer failures shouldn't break the pipeline
                print(f"Analyzer {analyzer.__class__.__name__} failed: {e}")
                continue
        
        # Build and return evidence bundle
        return EvidenceBundle(
            changed_symbols=all_changed_symbols,
            risk_anchors=all_risk_anchors,
            impact_evidence=all_impact_evidence,
            side_effects=all_side_effects,
            constraints=all_constraints,
            business_objects=all_business_objects,
        )


# Import here to avoid circular dependency
from core_engine.models.evidence_bundle import EvidenceBundle
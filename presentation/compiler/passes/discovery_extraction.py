"""Pass 1 — Discovery Extraction.

Responsibility:
    Convert Discovery objects from DiscoveryIR into PresentationDiscovery objects.

Input Contract:
    context.normalized_discoveries: list[Discovery]
        Fully-formed Discovery objects from the Discovery Compiler.

Output Contract:
    context.discoveries: list[PresentationDiscovery]
        Every Discovery becomes exactly one PresentationDiscovery.

Transformation:
    For each Discovery:
        1. Extract title from statement (first sentence or first 80 chars)
        2. Use full statement as summary
        3. Preserve all evidence
        4. Convert support measurements to metrics
        5. Convert ranking vector and surprise ratios
        6. Preserve metadata

Algorithm:
    discoveries = []
    for d in normalized_discoveries:
        title = extract_title(d.statement)
        metrics = convert_support_to_metrics(d.support)
        ranking_vector = convert_ranking_vector(d.support.ranking_vector)
        surprise = convert_surprise_ratios(d.support.surprise_ratios)
        
        discovery = PresentationDiscovery(
            id=d.id,
            kind=d.kind,
            title=title,
            summary=d.statement,
            evidence=d.evidence,
            metrics=metrics,
            ranking_vector=ranking_vector,
            surprise=surprise,
            metadata=d.metadata,
        )
        discoveries.append(discovery)
    return discoveries

Invariants:
    - Every Discovery becomes exactly one PresentationDiscovery.
    - No merging, no filtering, no ranking, no sorting.
    - Evidence is preserved verbatim — never dropped, never modified.

Failure Conditions:
    - If a DiscoveryKind has no mapping, use it directly.
      This ensures forward compatibility with new discovery kinds.

Complexity:
    O(N) where N = number of discoveries.

Must Never:
    - Analyze, rank, filter, sort, merge, compress, or summarize.
    - Interpret or infer new facts from evidence.
    - Drop or modify evidence.
"""
from __future__ import annotations

from operational.discovery.model import Discovery
from presentation.model import (
    PresentationDiscovery,
    PresentationEvidence,
    SignificanceMetrics,
    RankingVector,
    SurpriseVector,
)
from .base import PresentationPassContext, PresentationCompilationPass


class DiscoveryExtractionPass(PresentationCompilationPass):
    """
    Pass 1: Converts Discovery objects from DiscoveryIR into PresentationDiscovery objects.

    This pass exists to transform the Discovery representation into the
    Presentation Discovery model that the rest of the compiler operates on.
    """

    @property
    def name(self) -> str:
        return "discovery_extraction"

    def run(self, context: PresentationPassContext) -> PresentationPassContext:
        """Convert every Discovery into a presentation discovery."""
        normalized = context.normalized_discoveries
        if not normalized:
            return context

        discoveries: list[PresentationDiscovery] = []

        for d in normalized:
            if not isinstance(d, Discovery):
                continue
            
            # Extract a short title from the statement (first sentence or first 80 chars)
            statement = d.statement
            title = statement.split('.')[0] if '.' in statement else statement
            if len(title) > 80:
                title = title[:77] + "..."
            
            # Convert support measurements to metrics
            s = d.support
            metrics = SignificanceMetrics(
                execution_reach=s.execution_reach,
                fan_out=s.fan_out,
                propagation_depth=s.propagation_depth,
                boundary_crossings=s.boundary_crossings,
                sharedness=s.shared_by_count,
                external_surface=s.external_surface,
                data_surface=s.data_surface,
                validation_gap=s.validation_gaps,
                evidence_density=len(d.evidence),
                cross_domain_evidence=self._count_unique_sources(d.evidence),
            )
            
            # Convert ranking vector
            ranking_vector = None
            if s.ranking_vector:
                ranking_vector = RankingVector(
                    has_external_surface=s.ranking_vector[0] if len(s.ranking_vector) > 0 else 0,
                    execution_reach=s.ranking_vector[1] if len(s.ranking_vector) > 1 else 0,
                    boundary_crossings=s.ranking_vector[2] if len(s.ranking_vector) > 2 else 0,
                    propagation_depth=s.ranking_vector[3] if len(s.ranking_vector) > 3 else 0,
                    sharedness=s.ranking_vector[4] if len(s.ranking_vector) > 4 else 0,
                    has_validation_gap=s.ranking_vector[5] if len(s.ranking_vector) > 5 else 0,
                    evidence_density=s.ranking_vector[6] if len(s.ranking_vector) > 6 else 0,
                )
            
            # Convert surprise ratios
            surprise = None
            if s.surprise_ratios:
                ratios = s.surprise_ratios
                surprise = SurpriseVector(
                    reach_ratio=ratios.get("reach", 0.0),
                    propagation_ratio=ratios.get("propagation", 0.0),
                    boundary_ratio=ratios.get("boundary", 0.0),
                    fan_out_ratio=ratios.get("fan_out", 0.0),
                    service_ratio=ratios.get("service", 0.0),
                    max_ratio=max(ratios.values()) if ratios else 0.0,
                    description="High impact ratio detected" if max(ratios.values()) >= 5.0 else "",
                )
            
            discovery = PresentationDiscovery(
                id=d.id,
                kind=d.kind,
                title=title,
                summary=statement,
                evidence=d.evidence,
                metrics=metrics,
                ranking_vector=ranking_vector,
                surprise=surprise,
                metadata=d.metadata,
            )
            discoveries.append(discovery)

        context.discoveries = discoveries
        return context

    @staticmethod
    def _count_unique_sources(evidence: tuple[Any, ...]) -> int:
        """Count unique evidence sources."""
        sources = set()
        for e in evidence:
            if hasattr(e, 'source'):
                sources.add(e.source)
        return len(sources)
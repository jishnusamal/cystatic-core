"""Pass 3 — Ranking.

Responsibility:
    Order discoveries by importance using lexicographic ORDER BY.
    Not a single score — a RankingVector with component-wise comparison.

Input Contract:
    context.discoveries: list[PresentationDiscovery] (with metrics populated)
    context.significance_map: dict[str, SignificanceMetrics]

Output Contract:
    context.ranked_discovery_ids: list[str]
        Discovery IDs sorted by RankingVector descending (lexicographic).
    Every discovery has its ranking_vector populated.

Transformation:
    For each discovery, build a RankingVector from its SignificanceMetrics:
        has_external_surface: 1 if metrics.external_surface > 0 else 0
        execution_reach: metrics.execution_reach
        boundary_crossings: metrics.boundary_crossings
        propagation_depth: metrics.propagation_depth
        sharedness: metrics.sharedness
        has_validation_gap: 1 if metrics.validation_gap > 0 else 0
        evidence_density: metrics.evidence_density

    Sort by RankingVector descending (lexicographic).

Algorithm:
    for discovery in discoveries:
        metrics = significance_map[discovery.id]
        vector = RankingVector(
            has_external_surface=1 if metrics.external_surface > 0 else 0,
            execution_reach=metrics.execution_reach,
            boundary_crossings=metrics.boundary_crossings,
            propagation_depth=metrics.propagation_depth,
            sharedness=metrics.sharedness,
            has_validation_gap=1 if metrics.validation_gap > 0 else 0,
            evidence_density=metrics.evidence_density,
        )
        discovery.ranking_vector = vector

    discoveries.sort(key=lambda d: d.ranking_vector, reverse=True)
    ranked_ids = [d.id for d in discoveries]

Invariants:
    - Every discovery receives a RankingVector.
    - Sorting is purely lexicographic — no weights, no tuning, no ML.
    - Explainability is free: "This discovery ranked higher because both touched
      external behavior, but this one reached more execution paths."

Failure Conditions:
    - If significance_map is missing an entry, use default RankingVector (all zeros).
    - If no discoveries exist, return empty list.

Complexity:
    O(N log N) where N = number of discoveries.

Must Never:
    - Compute a single opaque score.
    - Use weights, tuning parameters, or machine learning.
    - Access renderer-specific formats.
"""
from __future__ import annotations

from presentation.model import (
    PresentationDiscovery,
    RankingVector,
    SignificanceMetrics,
)
from .base import PresentationPassContext, PresentationCompilationPass


class RankingPass(PresentationCompilationPass):
    """
    Pass 3: Ranks discoveries using lexicographic ORDER BY on RankingVector.

    Exactly like SQL: ORDER BY external_surface DESC, reach DESC, boundary DESC, ...
    No weights. No tuning. No machine learning.
    """

    @property
    def name(self) -> str:
        return "ranking"

    def run(self, context: PresentationPassContext) -> PresentationPassContext:
        """Rank all discoveries using lexicographic ORDER BY."""
        if not context.discoveries:
            return context

        # Build RankingVector for each discovery
        for discovery in context.discoveries:
            metrics = context.significance_map.get(discovery.id)
            vector = self._build_ranking_vector(discovery, metrics)
            context.update_discovery(discovery.id, ranking_vector=vector)

        # Sort by RankingVector descending (lexicographic)
        context.discoveries.sort(
            key=lambda d: d.ranking_vector or RankingVector(),
            reverse=True,
        )

        # Build ordered list of discovery IDs
        context.ranked_discovery_ids = [d.id for d in context.discoveries]
        return context

    def _build_ranking_vector(
        self,
        discovery: PresentationDiscovery,
        metrics: SignificanceMetrics | None,
    ) -> RankingVector:
        """Build a RankingVector from significance measurements."""
        if metrics is None:
            return RankingVector()

        return RankingVector(
            has_external_surface=1 if metrics.external_surface > 0 else 0,
            execution_reach=metrics.execution_reach,
            boundary_crossings=metrics.boundary_crossings,
            propagation_depth=metrics.propagation_depth,
            sharedness=metrics.sharedness,
            has_validation_gap=1 if metrics.validation_gap > 0.0 else 0,
            evidence_density=metrics.evidence_density,
        )
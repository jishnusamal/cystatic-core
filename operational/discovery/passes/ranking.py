"""RankingPass — orders discoveries by importance using lexicographic ORDER BY.

MOVED FROM: presentation/compiler/passes/ranking.py

Responsibility:
    Assign importance scores via lexicographic ORDER BY on DiscoverySupport.
    Not a single opaque score — component-wise comparison.

Input Contract:
    context.discoveries: list[Discovery] (with support populated)

Output Contract:
    Every discovery has its importance score set (0.0 to 1.0).
    Discoveries are sorted by importance descending.

Transformation:
    For each discovery, build a ranking vector from DiscoverySupport:
        has_external_surface: 1 if support.external_surface > 0 else 0
        execution_reach: support.execution_reach
        boundary_crossings: support.boundary_crossings
        propagation_depth: support.propagation_depth
        sharedness: support.shared_by_count
        has_validation_gap: 1 if support.validation_gaps > 0 else 0
        evidence_density: len(evidence)

    Sort by vector descending (lexicographic).
    Convert position to importance: importance = 1.0 - (index / max_index).

Algorithm:
    Exactly like SQL: ORDER BY external_surface DESC, reach DESC, boundary DESC, ...
    No weights. No tuning. No machine learning.
"""
from __future__ import annotations

from operational.discovery.model import (
    Discovery,
    DiscoverySupport,
)
from operational.discovery.passes.base import DiscoveryPassContext, DiscoveryCompilerPass


class RankingPass(DiscoveryCompilerPass):
    """Ranks discoveries using lexicographic ORDER BY on DiscoverySupport.

    No weights. No tuning. No machine learning.
    """

    @property
    def name(self) -> str:
        return "ranking"

    def run(self, context: DiscoveryPassContext) -> DiscoveryPassContext:
        """Rank all discoveries using lexicographic ORDER BY."""
        if not context.discoveries:
            return context

        # Build ranking vectors and sort
        def _ranking_key(d: Discovery) -> tuple:
            s = d.support
            return (
                1 if s.external_surface > 0 else 0,  # has_external_surface
                s.execution_reach,                     # execution_reach
                s.boundary_crossings,                  # boundary_crossings
                s.propagation_depth,                   # propagation_depth
                s.shared_by_count,                     # sharedness
                1 if s.validation_gaps > 0 else 0,     # has_validation_gap
                len(d.evidence),                       # evidence_density
            )

        # Sort by ranking key descending (lexicographic)
        context.discoveries.sort(key=_ranking_key, reverse=True)

        # Assign importance based on position (percentile)
        n = len(context.discoveries)
        if n > 1:
            updated: list[Discovery] = []
            for i, d in enumerate(context.discoveries):
                importance = round(1.0 - (i / (n - 1)), 2)
                updated.append(Discovery(
                    id=d.id,
                    kind=d.kind,
                    statement=d.statement,
                    importance=importance,
                    support=d.support,
                    evidence=d.evidence,
                    metadata=d.metadata,
                ))
            context.discoveries = updated
        elif n == 1:
            d = context.discoveries[0]
            context.discoveries = [Discovery(
                id=d.id, kind=d.kind, statement=d.statement,
                importance=1.0, support=d.support,
                evidence=d.evidence, metadata=d.metadata,
            )]

        return context
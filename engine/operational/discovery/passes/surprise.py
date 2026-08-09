"""SurpriseDetectionPass — identifies surprising discoveries by computing deterministic ratios.

MOVED FROM: presentation/compiler/passes/surprise_detection.py

Responsibility:
    Identify surprising discoveries by computing deterministic ratios between
    observable change and system impact. Pure measurements — no risk labels.

Input Contract:
    context.discoveries: list[Discovery] (with support populated)
    context.discovery_model: EngineeringDiscoveryModel

Output Contract:
    Every surprising discovery has its surprise_ratios populated in support.

Transformation:
    For each discovery, compute component ratios:
        reach_ratio: execution_reach / changed_symbols
        propagation_ratio: propagation_depth / changed_files
        boundary_ratio: boundary_crossings / changed_symbols
        fan_out_ratio: fan_out / changed_endpoints
        service_ratio: external_surface / changed_files

    max_ratio = max(all component ratios)
    If max_ratio >= MIN_SURPRISE_RATIO, mark as surprising.

Algorithm:
    for discovery in discoveries:
        support = discovery.support
        change_size = support.changed_symbol_count
        file_count = support.changed_file_count
        endpoint_count = count from model

        ratios = {
            "reach": support.execution_reach / max(change_size, 1),
            "propagation": support.propagation_depth / max(file_count, 1),
            "boundary": support.boundary_crossings / max(change_size, 1),
            "fan_out": support.fan_out / max(endpoint_count, 1),
            "service": support.external_surface / max(file_count, 1),
        }
        max_ratio = max(ratios.values())

        if max_ratio >= MIN_SURPRISE_RATIO:
            support.surprise_ratios = ratios
            boost importance

Invariants:
    - Surprise is a vector of pure ratios — no AI, no heuristics.
    - Never labels discoveries as "risky", "dangerous", or "problematic".

Must Never:
    - Use AI, heuristics, or risk assessment.
    - Label discoveries as risky, dangerous, or problematic.
"""
from __future__ import annotations

from engine.operational.discovery.model import (
    Discovery,
    DiscoverySupport,
)
from engine.operational.discovery.passes.base import DiscoveryPassContext, DiscoveryCompilerPass


class SurpriseDetectionPass(DiscoveryCompilerPass):
    """Detects deterministic surprises by comparing change size vs system impact.

    A surprise is a ratio between observable change size and observed system impact.
    High ratio = high surprise. Pure deterministic measurement.
    """

    # Minimum ratio to flag a discovery as surprising
    MIN_SURPRISE_RATIO: float = 5.0

    # Importance boost for surprising discoveries
    SURPRISE_BOOST: float = 0.2

    @property
    def name(self) -> str:
        return "surprise_detection"

    def run(self, context: DiscoveryPassContext) -> DiscoveryPassContext:
        """Detect surprising discoveries by computing ratio vectors."""
        model = context.discovery_model
        if not context.discoveries:
            return context

        # Get changed endpoint count from model
        endpoint_count = 0
        if model is not None and model.change is not None:
            endpoint_count = len(getattr(model.change, 'changed_endpoints', ()))

        updated: list[Discovery] = []
        for d in context.discoveries:
            s = d.support

            # Compute denominators
            change_size = max(s.changed_symbol_count, 1)
            file_count = max(s.changed_file_count, 1)
            ep_count = max(endpoint_count, 1)

            # Compute component ratios
            ratios: dict[str, float] = {}
            ratios["reach"] = self._safe_ratio(s.execution_reach, change_size)
            ratios["propagation"] = self._safe_ratio(s.propagation_depth, file_count)
            ratios["boundary"] = self._safe_ratio(s.boundary_crossings, change_size)
            ratios["fan_out"] = self._safe_ratio(s.fan_out, ep_count)
            ratios["service"] = self._safe_ratio(s.external_surface, file_count)

            max_ratio = max(ratios.values())

            new_support = DiscoverySupport(
                execution_reach=s.execution_reach,
                fan_in=s.fan_in,
                fan_out=s.fan_out,
                propagation_depth=s.propagation_depth,
                boundary_crossings=s.boundary_crossings,
                external_surface=s.external_surface,
                data_surface=s.data_surface,
                event_surface=s.event_surface,
                validation_coverage=s.validation_coverage,
                validation_gaps=s.validation_gaps,
                shared_by_count=s.shared_by_count,
                cross_service_count=s.cross_service_count,
                changed_symbol_count=s.changed_symbol_count,
                changed_file_count=s.changed_file_count,
                ranking_vector=s.ranking_vector,
                surprise_ratios=ratios if max_ratio >= self.MIN_SURPRISE_RATIO else {},
            )

            # Boost importance for surprising discoveries
            importance = d.importance
            if max_ratio >= self.MIN_SURPRISE_RATIO:
                importance = min(importance + self.SURPRISE_BOOST, 1.0)

            updated.append(Discovery(
                id=d.id,
                kind=d.kind,
                statement=d.statement,
                importance=importance,
                support=new_support,
                evidence=d.evidence,
                metadata=d.metadata,
            ))

        context.discoveries = updated
        return context

    @staticmethod
    def _safe_ratio(numerator: int, denominator: int) -> float:
        """Compute a ratio safely."""
        if denominator == 0:
            return 0.0
        return round(numerator / denominator, 1)
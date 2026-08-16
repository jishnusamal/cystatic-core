"""SignificanceEvaluationPass — measures significance attributes for every discovery.

MOVED FROM: presentation/compiler/passes/significance_evaluation.py

Responsibility:
    Populate DiscoverySupport measurements for every discovery.
    Measurements are read from the EngineeringDiscoveryModel.
    Not importance — those are different. Importance belongs to ranking.

Input Contract:
    context.discoveries: list[Discovery] (with support fields from prior passes)
    context.discovery_model: EngineeringDiscoveryModel

Output Contract:
    Every discovery has its support fields fully populated with
    measurements from the model.

Transformation:
    For each discovery, cross-reference its metadata (symbol_id, behavior_id)
    against the EngineeringDiscoveryModel to populate:
        execution_reach, fan_in, fan_out, propagation_depth,
        boundary_crossings, external_surface, data_surface,
        validation_gaps, shared_by_count

Invariants:
    - Metrics are raw measurements — never normalized, never weighted, never scored.
    - No interpretation occurs — only deterministic computation from compiler outputs.

Must Never:
    - Compute a single "significance score" or "importance score".
    - Normalize, weight, or combine metrics into a single value.
    - Rank or order discoveries.
"""

from __future__ import annotations

from engine.operational.discovery.model import (
    Discovery,
    DiscoverySupport,
)
from engine.operational.discovery.passes.base import (
    DiscoveryCompilerPass,
    DiscoveryPassContext,
)


class SignificanceEvaluationPass(DiscoveryCompilerPass):
    """Populates DiscoverySupport measurements for every discovery.

    These are raw measurements — not scores, not weights, not ranks.
    Every metric is directly computed from compiler outputs.
    """

    @property
    def name(self) -> str:
        return "significance_evaluation"

    def run(self, context: DiscoveryPassContext) -> DiscoveryPassContext:
        """Populate support measurements for all discoveries."""
        model = context.discovery_model
        if model is None or not context.discoveries:
            return context

        behavior = model.behavior
        change = model.change
        dependency = getattr(model, "dependency", None)
        api = getattr(model, "api", None)
        data = getattr(model, "data", None)
        validation = getattr(model, "validation", None)
        event = getattr(model, "event", None)

        # Pre-compute model-level aggregates
        total_behaviors = len(getattr(behavior, "behaviors", ())) if behavior else 0
        total_changed = (
            (
                len(getattr(change, "added_symbols", ()))
                + len(getattr(change, "removed_symbols", ()))
                + len(getattr(change, "modified_symbols", ()))
            )
            if change
            else 0
        )
        exec_depth = getattr(behavior, "execution_depth", 0) if behavior else 0

        fan_in_data: dict[str, int] = {}
        fan_out_data: dict[str, int] = {}
        cross_service_count = 0
        if dependency is not None:
            fan_in_data = getattr(dependency, "fan_in", {})
            fan_out_data = getattr(dependency, "fan_out", {})
            cross_service_count = len(
                getattr(dependency, "cross_service_references", ())
            )

        api_endpoint_count = 0
        if api is not None:
            api_endpoint_count = (
                len(getattr(api, "rest", ()))
                + len(getattr(api, "graphql", ()))
                + len(getattr(api, "rpc", ()))
            )

        data_entity_count = 0
        if data is not None:
            data_entity_count = self._count_attr(data, ("models", "tables", "entities"))

        validation_gaps = 0
        if validation is not None:
            validation_gaps = self._count_attr(
                validation, ("gaps", "missing_coverage", "uncovered")
            )

        event_count = 0
        if event is not None:
            pub = getattr(event, "published_events", ())
            con = getattr(event, "consumed_events", ())
            event_count = len(pub) + len(con)

        # Enrich each discovery with model-level measurements
        updated_discoveries: list[Discovery] = []
        for d in context.discoveries:
            support = d.support

            # Extract symbol_id from metadata if present
            symbol_id = d.metadata.get("symbol_id", "")

            # Populate from model-level data where not already set
            new_support = DiscoverySupport(
                execution_reach=support.execution_reach or total_behaviors,
                fan_in=support.fan_in or fan_in_data.get(symbol_id, 0),
                fan_out=support.fan_out or fan_out_data.get(symbol_id, 0),
                propagation_depth=support.propagation_depth or exec_depth,
                boundary_crossings=support.boundary_crossings or cross_service_count,
                external_surface=support.external_surface or api_endpoint_count,
                data_surface=support.data_surface or data_entity_count,
                event_surface=support.event_surface or event_count,
                validation_coverage=support.validation_coverage,
                validation_gaps=support.validation_gaps or validation_gaps,
                shared_by_count=support.shared_by_count,
                cross_service_count=support.cross_service_count or cross_service_count,
                changed_symbol_count=support.changed_symbol_count or total_changed,
                changed_file_count=support.changed_file_count,
                ranking_vector=support.ranking_vector,
                surprise_ratios=support.surprise_ratios,
            )

            updated_discoveries.append(
                Discovery(
                    id=d.id,
                    kind=d.kind,
                    statement=d.statement,
                    importance=d.importance,
                    support=new_support,
                    evidence=d.evidence,
                    metadata=d.metadata,
                )
            )

        context.discoveries = updated_discoveries
        return context

    @staticmethod
    def _count_attr(obj: object, attr_names: tuple[str, ...]) -> int:
        """Count items from the first matching attribute name."""
        for name in attr_names:
            if hasattr(obj, name):
                items = getattr(obj, name)
                if isinstance(items, (list, tuple, set, frozenset)):
                    return len(items)
                if hasattr(items, "__len__"):
                    return len(items)
                return 1 if items else 0
        return 0

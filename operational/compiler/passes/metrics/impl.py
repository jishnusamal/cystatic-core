"""Metrics Compilation Pass - compiles observable discovery metrics.

Question: How much engineering discovery does this change require?

Produces DiscoveryMetrics with:
- Behaviors: count of affected behaviors
- Services: count of distinct services affected
- Dependency Fan-out: total dependency fan-out
- Execution Depth: max execution depth
- Data Stores: count of distinct data stores
- Events: count of events
- APIs: count of affected API endpoints
- Validation Breadth: count of test files
- Traversal Size: total symbols traversed

These are observable metrics, not scores or judgments.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from operational.compiler.passes.base import (
    OperationalCompilerPass,
    OperationalPassContext,
)
from language_adapters.model import Symbol


@dataclass(frozen=True)
class DiscoveryMetrics:
    """
    Observable metrics about the engineering discovery required.

    All fields are counts or sizes derived from the other models.
    No scores, no judgments.
    """

    # Number of affected behaviors
    behaviors: int = 0

    # Number of distinct services affected
    services: int = 0

    # Total dependency fan-out (sum of all fan-out)
    dependency_fan_out: int = 0

    # Maximum execution depth from entry points to changed symbols
    execution_depth: int = 0

    # Number of distinct data stores referenced
    data_stores: int = 0

    # Number of events (published + consumed)
    events: int = 0

    # Number of affected API endpoints (all types)
    apis: int = 0

    # Number of test files/validations covering the change
    validation_breadth: int = 0

    # Total number of symbols traversed during analysis
    traversal_size: int = 0


class MetricsCompilationPass(OperationalCompilerPass):
    """
    Pass 6 of Operational compilation.

    Aggregates observable discovery metrics from all prior passes.
    """

    @property
    def name(self) -> str:
        return "metrics_compilation"

    def validate_input(self, context: OperationalPassContext) -> bool:
        """Verify the composed model exists."""
        return context.composed_model is not None

    def run(self, context: OperationalPassContext) -> OperationalPassContext:
        """
        Compute discovery metrics from the enriched model.

        Args:
            context: Pass context with all prior models populated.

        Returns:
            Updated context with discovery metrics set on composed_model.
        """
        if not self.validate_input(context):
            return context

        model = context.composed_model

        # 1. Behavior count
        behaviors = len(model.behavior.behaviors)

        # 2. Service count (from dependency model)
        services = 0
        if model.dependency is not None:
            # Count distinct services from cross-service references
            services_in_refs: set[str] = set()
            for src, tgt, _sid in model.dependency.cross_service_references:
                services_in_refs.add(src)
                services_in_refs.add(tgt)
            services = len(services_in_refs) if services_in_refs else 1

        # 3. Dependency fan-out
        dependency_fan_out = 0
        if model.dependency is not None:
            dependency_fan_out = sum(model.dependency.fan_out.values())

        # 4. Execution depth
        execution_depth = 0
        if model.dependency is not None:
            execution_depth = model.dependency.dependency_depth

        # 5. Data stores
        data_stores = 0
        if model.data is not None:
            data_stores = len(model.data.external_storage)
            if model.data.tables:
                data_stores = max(data_stores, len(model.data.tables))

        # 6. Events
        events = 0
        if model.event is not None:
            events = len(model.event.published_events) + len(model.event.consumed_events)

        # 7. APIs
        apis = 0
        if model.api is not None:
            apis = (
                len(model.api.rest)
                + len(model.api.graphql)
                + len(model.api.rpc)
                + len(model.api.cli)
                + len(model.api.cron)
                + len(model.api.workers)
            )

        # 8. Validation breadth
        validation_breadth = 0
        if model.validation is not None:
            validation_breadth = (
                len(model.validation.unit_tests)
                + len(model.validation.integration_tests)
                + len(model.validation.e2e_tests)
                + len(model.validation.benchmarks)
            )

        # 9. Traversal size: total symbols analyzed
        traversal_size = 0
        if model.dependency is not None:
            traversal_size = (
                len(model.dependency.callers)
                + len(model.dependency.dependents)
            )
        traversal_size += len(model.repository.symbols)

        metrics = DiscoveryMetrics(
            behaviors=behaviors,
            services=services,
            dependency_fan_out=dependency_fan_out,
            execution_depth=execution_depth,
            data_stores=data_stores,
            events=events,
            apis=apis,
            validation_breadth=validation_breadth,
            traversal_size=traversal_size,
        )

        # Enrich the composed model with metrics
        context.composed_model = model.__class__(
            repository=model.repository,
            change=model.change,
            behavior=model.behavior,
            dependency=model.dependency,
            data=model.data,
            event=model.event,
            validation=model.validation,
            api=model.api if hasattr(model, 'api') else None,
            metrics=metrics,
        )

        # Also store in metadata for backward compatibility
        context.metadata["discovery_metrics"] = metrics

        return context
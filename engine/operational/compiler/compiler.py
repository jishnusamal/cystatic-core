"""Operational Compiler - orchestrates compilation passes.

Transforms deterministic models (Repository, Change, Behavior) into a single
immutable OperationalChangeModel enriched with dependency, data, event, API,
validation, and metrics models.

This is the linker and compilation stage in the factor-api compilation pipeline.
"""

from typing import Any, cast

from engine.operational.model import OperationalChangeModel

from .passes import (
    APICompilationPass,
    ConsistencyValidationPass,
    DataCompilationPass,
    DependencyCompilationPass,
    EventCompilationPass,
    MetricsCompilationPass,
    ModelCompositionPass,
    OperationalPassContext,
    ValidationCompilationPass,
)


class OperationalCompiler:
    """
    Compiles RepositoryDelta + ChangeModel + BehaviorModel into
    an enriched OperationalChangeModel.

    This is the main entry point for operational compilation.
    It orchestrates the execution of all compiler passes in order.

    Pass groups:
    1. Composition: Model composition + consistency validation
    2. Enrichment: Dependency, data, event, API, validation, and metrics compilation

    Input: RepositoryDelta + ChangeModel + BehaviorModel
    Output: OperationalChangeModel with all optional models populated
    """

    def __init__(self):
        """Initialize the compiler with all passes."""
        self.passes = [
            # Composition group
            ModelCompositionPass(),
            ConsistencyValidationPass(),
            # Enrichment group
            DependencyCompilationPass(),
            DataCompilationPass(),
            EventCompilationPass(),
            APICompilationPass(),
            ValidationCompilationPass(),
            MetricsCompilationPass(),
        ]

    def compile(
        self,
        repository_model: Any = None,
        change_model: Any = None,
        behavior_model: Any = None,
        repository_delta: Any = None,
        repository_query: Any = None,
    ) -> OperationalChangeModel:
        """
        Compile deterministic models into an enriched OperationalChangeModel.
        """
        # Support both old and new interface for backward compatibility
        head_model: Any = None
        if repository_delta is not None:
            head_model = getattr(repository_delta, "head_model", None)
        elif repository_model is not None:
            head_model = repository_model
        elif repository_query is not None:
            head_model = repository_query

        if head_model is None and repository_query is not None:
            head_model = repository_query

        if head_model is None:
            raise ValueError(
                "Either repository_delta, repository_model, or repository_query must be provided"
            )

        # Initialize pass context with models
        context = OperationalPassContext(
            repository_model=head_model,
            repository_delta=repository_delta,
            change_model=change_model,
            behavior_model=behavior_model,
            metadata={
                "repository_model": head_model,
                "repository_delta": repository_delta,
                "change_model": change_model,
                "behavior_model": behavior_model,
                "repository_query": repository_query,
            },
        )

        # Execute each pass in sequence
        for compiler_pass in self.passes:
            import time

            start_time = time.perf_counter()
            print(f"[timer] START {compiler_pass.name}")
            context = compiler_pass.run(context)
            duration_ms = (time.perf_counter() - start_time) * 1000
            print(f"[timer] END {compiler_pass.name} {duration_ms:.2f}ms")

        # Check for consistency errors
        if context.has_consistency_errors:
            error_details = "\n".join(context.consistency_errors)
            raise ValueError(
                f"Consistency validation failed with "
                f"{len(context.consistency_errors)} error(s):\n{error_details}"
            )

        # Return the enriched model
        return cast(OperationalChangeModel, context.composed_model)

    def compile_with_errors(
        self,
        repository_model: Any = None,
        change_model: Any = None,
        behavior_model: Any = None,
        repository_delta: Any = None,
        repository_query: Any = None,
    ) -> tuple[OperationalChangeModel | None, list[str]]:
        # Support both old and new interface for backward compatibility
        head_model: Any = None
        if repository_delta is not None:
            head_model = getattr(repository_delta, "head_model", None)
        elif repository_model is not None:
            head_model = repository_model
        elif repository_query is not None:
            head_model = repository_query

        if head_model is None and repository_query is not None:
            head_model = repository_query

        if head_model is None:
            raise ValueError(
                "Either repository_delta, repository_model, or repository_query must be provided"
            )

        context = OperationalPassContext(
            repository_model=head_model,
            repository_delta=repository_delta,
            change_model=change_model,
            behavior_model=behavior_model,
        )

        for compiler_pass in self.passes:
            import time

            start_time = time.perf_counter()
            print(f"[timer] START {compiler_pass.name}")
            context = compiler_pass.run(context)
            duration_ms = (time.perf_counter() - start_time) * 1000
            print(f"[timer] END {compiler_pass.name} {duration_ms:.2f}ms")

        if context.has_consistency_errors:
            return None, context.consistency_errors

        return context.composed_model, []

    def get_pass_names(self) -> list[str]:
        """Get the names of all passes in execution order."""
        return [pass_.name for pass_ in self.passes]

    def get_discovery_metrics(self, context: OperationalPassContext) -> Any | None:
        """Get discovery metrics from a pass context."""
        return context.discovery_metrics

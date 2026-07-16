"""Operational Compiler - orchestrates compilation passes.

Transforms deterministic models (Repository, Change, Behavior) into a single
immutable OperationalChangeModel enriched with dependency, data, event, API,
validation, and metrics models.

This is the linker and compilation stage in the cystatic compilation pipeline.
"""

from typing import Any, cast

from behavior.model import BehaviorModel
from change.model import ChangeModel, RepositoryDelta
from language_adapters.model import RepositoryModel
from operational.model import OperationalChangeModel

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
        repository_model: RepositoryModel | None = None,
        change_model: ChangeModel | None = None,
        behavior_model: BehaviorModel | None = None,
        repository_delta: RepositoryDelta | None = None,
    ) -> OperationalChangeModel:
        """
        Compile deterministic models into an enriched OperationalChangeModel.

        Args:
            repository_model: RepositoryModel (deprecated, use repository_delta)
            change_model: ChangeModel
            behavior_model: BehaviorModel
            repository_delta: RepositoryDelta containing both base and head models

        Returns:
            OperationalChangeModel with all optional models populated

        Raises:
            ValueError: If consistency validation fails
        """
        # Support both old and new interface for backward compatibility
        if repository_delta is not None:
            head_model = repository_delta.head_model
        else:
            head_model = repository_model

        # Type checker: ensure head_model is not None
        if head_model is None:
            raise ValueError("Either repository_delta or repository_model must be provided")

        # Initialize pass context with models
        context = OperationalPassContext(
            repository_model=head_model,
            repository_delta=repository_delta,
            change_model=change_model,
            behavior_model=behavior_model,
            metadata={
                'repository_model': head_model,
                'repository_delta': repository_delta,
                'change_model': change_model,
                'behavior_model': behavior_model,
            }
        )

        # Execute each pass in sequence
        for compiler_pass in self.passes:
            context = compiler_pass.run(context)

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
        repository_model: RepositoryModel | None = None,
        change_model: ChangeModel | None = None,
        behavior_model: BehaviorModel | None = None,
        repository_delta: RepositoryDelta | None = None,
    ) -> tuple[OperationalChangeModel | None, list[str]]:
        """
        Compile and return errors instead of raising.

        This is useful when callers want to inspect validation failures
        without exception handling.

        Args:
            repository_model: RepositoryModel (deprecated, use repository_delta)
            change_model: ChangeModel
            behavior_model: BehaviorModel
            repository_delta: RepositoryDelta containing both base and head models

        Returns:
            Tuple of (OperationalChangeModel or None, list of error strings)
        """
        # Support both old and new interface for backward compatibility
        if repository_delta is not None:
            head_model = repository_delta.head_model
        else:
            head_model = repository_model

        # Type checker: ensure head_model is not None
        if head_model is None:
            raise ValueError("Either repository_delta or repository_model must be provided")

        context = OperationalPassContext(
            repository_model=head_model,
            repository_delta=repository_delta,
            change_model=change_model,
            behavior_model=behavior_model,
        )

        for compiler_pass in self.passes:
            context = compiler_pass.run(context)

        if context.has_consistency_errors:
            return None, context.consistency_errors

        return context.composed_model, []

    def get_pass_names(self) -> list[str]:
        """Get the names of all passes in execution order."""
        return [pass_.name for pass_ in self.passes]

    def get_discovery_metrics(self, context: OperationalPassContext) -> Any | None:
        """Get discovery metrics from a pass context."""
        return context.discovery_metrics
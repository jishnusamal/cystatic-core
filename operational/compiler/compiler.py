"""Operational Compiler - orchestrates Phase 4/5 compilation passes.

Transforms deterministic models (Repository, Change, Behavior) into a single
immutable OperationalChangeModel enriched with dependency, data, event, API,
validation, and metrics models.

This is the linker and analysis stage in the cystatic compilation pipeline.
"""

from typing import Any

from behavior.model import BehaviorModel
from change.model import ChangeModel
from language_adapters.model import RepositoryModel
from operational.model import OperationalChangeModel

from .passes import (
    APIAnalysisPass,
    ConsistencyValidationPass,
    DataAnalysisPass,
    DependencyAnalysisPass,
    EventAnalysisPass,
    MetricsPass,
    ModelCompositionPass,
    OperationalPassContext,
    ValidationAnalysisPass,
)


class OperationalCompiler:
    """
    Compiles RepositoryModel + ChangeModel + BehaviorModel into
    an enriched OperationalChangeModel.

    This is the main entry point for Phase 4/5 compilation.
    It orchestrates the execution of all compiler passes in order.

    Phase 4: Model composition + consistency validation
    Phase 5: Dependency, data, event, API, validation, and metrics analysis

    Input: RepositoryModel + ChangeModel + BehaviorModel
    Output: OperationalChangeModel with all optional models populated
    """

    def __init__(self):
        """Initialize the compiler with all passes."""
        self.passes = [
            # Phase 4: Composition
            ModelCompositionPass(),
            ConsistencyValidationPass(),
            # Phase 5: Operational Analysis
            DependencyAnalysisPass(),
            DataAnalysisPass(),
            EventAnalysisPass(),
            APIAnalysisPass(),
            ValidationAnalysisPass(),
            MetricsPass(),
        ]

    def compile(
        self,
        repository_model: RepositoryModel,
        change_model: ChangeModel,
        behavior_model: BehaviorModel,
    ) -> OperationalChangeModel:
        """
        Compile deterministic models into an enriched OperationalChangeModel.

        Args:
            repository_model: RepositoryModel from Phase 1 compilation
            change_model: ChangeModel from Phase 2 compilation
            behavior_model: BehaviorModel from Phase 3 compilation

        Returns:
            OperationalChangeModel with all Phase 5 models populated

        Raises:
            ValueError: If consistency validation fails
        """
        # Initialize pass context with models
        context = OperationalPassContext(
            repository_model=repository_model,
            change_model=change_model,
            behavior_model=behavior_model,
            metadata={
                'repository_model': repository_model,
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
        return context.composed_model

    def compile_with_errors(
        self,
        repository_model: RepositoryModel,
        change_model: ChangeModel,
        behavior_model: BehaviorModel,
    ) -> tuple[OperationalChangeModel | None, list[str]]:
        """
        Compile and return errors instead of raising.

        This is useful when callers want to inspect validation failures
        without exception handling.

        Args:
            repository_model: RepositoryModel from Phase 1 compilation
            change_model: ChangeModel from Phase 2 compilation
            behavior_model: BehaviorModel from Phase 3 compilation

        Returns:
            Tuple of (OperationalChangeModel or None, list of error strings)
        """
        context = OperationalPassContext(
            repository_model=repository_model,
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

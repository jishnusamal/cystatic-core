"""Engineering Discovery Compiler - produces the final EngineeringDiscoveryModel.

This compiler is a projection-only pass that transforms the OperationalChangeModel
into an EngineeringDiscoveryModel with all execution-oriented abstractions.
"""

from __future__ import annotations

from typing import Any, cast

from engine.behavior.model import BehaviorModel
from engine.change.model import ChangeModel, RepositoryDelta
from engine.repository.model import RepositoryModel
from engine.operational.model import OperationalChangeModel, EngineeringDiscoveryModel

from .passes import (
    OperationalPassContext,
    DependencyCompilationPass,
    DataCompilationPass,
    EventCompilationPass,
    APICompilationPass,
    ValidationCompilationPass,
    MetricsCompilationPass,
)


class EngineeringDiscoveryCompiler:
    """
    Compiles an OperationalChangeModel into an EngineeringDiscoveryModel.

    This is a projection-only compiler that extracts execution-oriented
    abstractions from the operational model.

    Input: OperationalChangeModel (or the components to build one)
    Output: EngineeringDiscoveryModel

    The compiler is deterministic and stateless. Same inputs always produce
    the same output model.
    """

    def __init__(self) -> None:
        """Initialize the compiler with all enrichment passes."""
        self.passes = [
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
    ) -> EngineeringDiscoveryModel:
        """
        Compile into an EngineeringDiscoveryModel.

        Args:
            repository_model: RepositoryModel (deprecated, use repository_delta).
            change_model: ChangeModel describing what changed.
            behavior_model: BehaviorModel describing affected behaviors.
            repository_delta: RepositoryDelta containing both base and head models.

        Returns:
            EngineeringDiscoveryModel with all execution-oriented abstractions.

        Raises:
            ValueError: If required models are missing.
        """
        # Support both old and new interface for backward compatibility
        head_model: RepositoryModel | None
        if repository_delta is not None:
            head_model = repository_delta.head_model
        else:
            head_model = repository_model

        if head_model is None:
            raise ValueError(
                "Either repository_delta or repository_model must be provided"
            )

        # After None check, head_model is guaranteed to be RepositoryModel
        if change_model is None:
            raise ValueError("change_model is required")
        if behavior_model is None:
            raise ValueError("behavior_model is required")

        # Build the operational model first
        operational_model = self._build_operational_model(
            head_model,  # type: ignore[arg-type]
            change_model,
            behavior_model,
            repository_delta,
        )

        # Create the engineering discovery model
        return self._build_discovery_model(operational_model)

    def from_operational_model(
        self, operational_model: OperationalChangeModel
    ) -> EngineeringDiscoveryModel:
        """
        Compile directly from an OperationalChangeModel.

        This is the primary entry point when the pipeline already has a
        composed OperationalChangeModel. Enrichment passes are run if the
        model doesn't already have enrichment models populated.

        Args:
            operational_model: The OperationalChangeModel to project.

        Returns:
            EngineeringDiscoveryModel with all execution-oriented abstractions.

        Raises:
            ValueError: If OperationalChangeModel is missing required models.
        """
        if not operational_model.has_all_required_models():
            raise ValueError("OperationalChangeModel is missing required models")

        # If enrichment models are not yet populated, run enrichment passes
        if not operational_model.populated_optional_models:
            enriched_model = self._enrich_from_model(operational_model)
            return self._build_discovery_model(enriched_model)

        return self._build_discovery_model(operational_model)

    def _enrich_from_model(
        self,
        operational_model: OperationalChangeModel,
    ) -> OperationalChangeModel:
        """
        Run enrichment passes on an existing OperationalChangeModel.

        Args:
            operational_model: The base OperationalChangeModel to enrich.

        Returns:
            Enriched OperationalChangeModel with all optional models populated.
        """
        # Initialize pass context with models from the OCM
        context = OperationalPassContext(
            repository_model=operational_model.repository,
            change_model=operational_model.change,
            behavior_model=operational_model.behavior,
            composed_model=operational_model,
        )

        # Run all enrichment passes
        for compiler_pass in self.passes:
            context = compiler_pass.run(context)

        return cast(OperationalChangeModel, context.composed_model)

    def _build_operational_model(
        self,
        repository_model: RepositoryModel,
        change_model: ChangeModel,
        behavior_model: BehaviorModel,
        repository_delta: RepositoryDelta | None,
    ) -> OperationalChangeModel:
        """
        Build the operational model by running enrichment passes.

        Args:
            repository_model: RepositoryModel.
            change_model: ChangeModel.
            behavior_model: BehaviorModel.
            repository_delta: RepositoryDelta.

        Returns:
            OperationalChangeModel with all enrichment models populated.
        """
        # Initialize pass context with models
        context = OperationalPassContext(
            repository_model=repository_model,
            repository_delta=repository_delta,
            change_model=change_model,
            behavior_model=behavior_model,
        )

        # Run the composition pass first to create the base model
        from .passes import ModelCompositionPass

        context = ModelCompositionPass().run(context)

        # Run all enrichment passes
        for compiler_pass in self.passes:
            context = compiler_pass.run(context)

        return cast(OperationalChangeModel, context.composed_model)

    def _build_discovery_model(
        self,
        operational_model: OperationalChangeModel,
    ) -> EngineeringDiscoveryModel:
        """
        Build the EngineeringDiscoveryModel from the operational model.

        This is a projection-only operation that extracts execution-oriented
        abstractions from the behavior model.

        Args:
            operational_model: The OperationalChangeModel.

        Returns:
            EngineeringDiscoveryModel.
        """
        behavior = operational_model.behavior
        execution_chains = getattr(behavior, "execution_chains", ())
        entry_points = getattr(behavior, "entry_points", ())
        terminal_points = getattr(behavior, "terminal_points", ())
        shared_executions = getattr(behavior, "shared_executions", ())
        reachable_units = getattr(behavior, "reachable_units", frozenset())
        execution_depth = getattr(behavior, "execution_depth", 0)

        execution_units = (
            tuple(u for chain in execution_chains for u in chain.units)
            if execution_chains
            else ()
        )

        return EngineeringDiscoveryModel(
            repository=operational_model.repository,
            change=operational_model.change,
            behavior=operational_model.behavior,
            operational=operational_model,
            execution_units=execution_units,
            execution_chains=execution_chains,
            entry_points=entry_points,
            terminal_points=terminal_points,
            shared_executions=shared_executions,
            reachable_units=reachable_units,
            execution_depth=execution_depth,
            dependency=operational_model.dependency,
            data=operational_model.data,
            event=operational_model.event,
            api=operational_model.api,
            validation=operational_model.validation,
            metrics=operational_model.metrics,
        )

    def get_pass_names(self) -> list[str]:
        """Get the names of all passes in execution order."""
        return [pass_.name for pass_ in self.passes]

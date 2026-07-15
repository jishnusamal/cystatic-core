"""Engineering Discovery Compiler - produces the final EngineeringDiscoveryArtifact.

This compiler is a projection-only pass that transforms the OperationalChangeModel
into an EngineeringDiscoveryArtifact with all execution-oriented abstractions.
"""

from typing import Any, cast

from behavior.model import BehaviorModel
from change.model import ChangeModel, RepositoryDelta
from language_adapters.model import RepositoryModel
from operational.model import OperationalChangeModel, EngineeringDiscoveryArtifact

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
    Compiles an OperationalChangeModel into an EngineeringDiscoveryArtifact.

    This is a projection-only compiler that extracts execution-oriented
    abstractions from the operational model.

    Input: OperationalChangeModel (or the components to build one)
    Output: EngineeringDiscoveryArtifact
    """

    def __init__(self):
        """Initialize the compiler with all passes."""
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
    ) -> EngineeringDiscoveryArtifact:
        """
        Compile into an EngineeringDiscoveryArtifact.

        Args:
            repository_model: RepositoryModel (deprecated, use repository_delta)
            change_model: ChangeModel
            behavior_model: BehaviorModel
            repository_delta: RepositoryDelta containing both base and head models

        Returns:
            EngineeringDiscoveryArtifact with all execution-oriented abstractions
        """
        # Support both old and new interface for backward compatibility
        if repository_delta is not None:
            head_model = repository_delta.head_model
        else:
            head_model = repository_model

        # Build the operational model first
        operational_model = self._build_operational_model(
            head_model, change_model, behavior_model, repository_delta
        )

        # Create the engineering discovery artifact
        return self._build_artifact(operational_model)

    def _build_operational_model(
        self,
        repository_model: RepositoryModel | None,
        change_model: ChangeModel | None,
        behavior_model: BehaviorModel | None,
        repository_delta: RepositoryDelta | None,
    ) -> OperationalChangeModel:
        """
        Build the operational model by running all passes.

        Args:
            repository_model: RepositoryModel
            change_model: ChangeModel
            behavior_model: BehaviorModel
            repository_delta: RepositoryDelta

        Returns:
            OperationalChangeModel
        """
        # Initialize pass context with models
        context = OperationalPassContext(
            repository_model=repository_model,
            repository_delta=repository_delta,
            change_model=change_model,
            behavior_model=behavior_model,
            metadata={
                'repository_model': repository_model,
                'repository_delta': repository_delta,
                'change_model': change_model,
                'behavior_model': behavior_model,
            }
        )

        # Run the composition pass first
        from .passes import ModelCompositionPass
        context = ModelCompositionPass().run(context)

        # Run all enrichment passes
        for compiler_pass in self.passes:
            context = compiler_pass.run(context)

        return cast(OperationalChangeModel, context.composed_model)

    def _build_artifact(
        self,
        operational_model: OperationalChangeModel,
    ) -> EngineeringDiscoveryArtifact:
        """
        Build the EngineeringDiscoveryArtifact from the operational model.

        Args:
            operational_model: The OperationalChangeModel

        Returns:
            EngineeringDiscoveryArtifact
        """
        # Extract execution-oriented abstractions from behavior model
        execution_units = list(operational_model.behavior.execution_chains)
        for chain in operational_model.behavior.execution_chains:
            execution_units.extend(chain.units)

        return EngineeringDiscoveryArtifact(
            repository=operational_model.repository,
            change=operational_model.change,
            behavior=operational_model.behavior,
            execution_units=tuple(
                u for chain in operational_model.behavior.execution_chains
                for u in chain.units
            ),
            execution_chains=operational_model.behavior.execution_chains,
            entry_points=operational_model.behavior.entry_points,
            terminal_points=operational_model.behavior.terminal_points,
            shared_executions=operational_model.behavior.shared_executions,
            reachable_units=operational_model.behavior.reachable_units,
            execution_depth=operational_model.behavior.execution_depth,
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
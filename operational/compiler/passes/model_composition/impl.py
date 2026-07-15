"""Pass 1 — Model Composition.

Question: How do the existing deterministic models relate?

Produces an OperationalChangeModel by composing RepositoryModel,
ChangeModel, and BehaviorModel into a single artifact.

No inference. No traversal. No graph analysis.
Just deterministic composition.
"""

from operational.compiler.passes.base import (
    OperationalCompilerPass,
    OperationalPassContext,
)
from operational.model import OperationalChangeModel
from language_adapters.model import RepositoryModel
from change.model import ChangeModel
from behavior.model import BehaviorModel


class ModelCompositionPass(OperationalCompilerPass):
    """
    Pass 1 of Operational compilation.

    Composes the three deterministic models (repository, change, behavior) into a single
    immutable OperationalChangeModel.
    """

    @property
    def name(self) -> str:
        return "model_composition"

    def validate_input(self, context: OperationalPassContext) -> bool:
        """Verify all three required models are present before composition."""
        if context.repository_model is None:
            return False
        if context.change_model is None:
            return False
        if context.behavior_model is None:
            return False
        return True

    def run(self, context: OperationalPassContext) -> OperationalPassContext:
        """
        Compose the three deterministic models into an OperationalChangeModel.

        Args:
            context: Pass context with repository_model, change_model,
                     and behavior_model populated.

        Returns:
            Updated context with composed_model set.

        Raises:
            ValueError: If any required model is missing.
        """
        if not self.validate_input(context):
            missing = []
            if context.repository_model is None:
                missing.append("repository_model")
            if context.change_model is None:
                missing.append("change_model")
            if context.behavior_model is None:
                missing.append("behavior_model")
            raise ValueError(
                f"Cannot compose models: missing {', '.join(missing)}"
            )

        context.composed_model = OperationalChangeModel(
            repository=context.repository_model,  # type: ignore[arg-type]
            change=context.change_model,  # type: ignore[arg-type]
            behavior=context.behavior_model,  # type: ignore[arg-type]
        )

        return context
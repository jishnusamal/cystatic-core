"""Behavior compiler - orchestrates compilation passes."""

from typing import Any

from .passes import (
    BehaviorPassContext,
    BehaviorCompilationPass,
    BehaviorGraphPass,
)
from behavior.model import BehaviorModel
from language_adapters.model import RepositoryModel


class BehaviorCompiler:
    """
    Compiles a Change Model + Repository Model into a Behavior Model.

    This is the main entry point for Phase 3 compilation.
    It orchestrates the execution of all compilation passes in order.

    Input: ChangeModel + RepositoryModel
    Output: BehaviorModel containing affected behaviors and execution graphs
    """

    def __init__(self):
        """Initialize the compiler with all passes."""
        self.passes = [
            BehaviorCompilationPass(),
            BehaviorGraphPass(),
        ]

    def compile(
        self,
        change_model: Any,
        repository_model: Any,
    ) -> BehaviorModel:
        """
        Compile changes into a Behavior Model.

        Args:
            change_model: ChangeModel from Phase 2 compilation
            repository_model: RepositoryModel from Phase 1 compilation

        Returns:
            BehaviorModel containing affected behaviors and execution graphs
        """
        # Initialize pass context with models
        context = BehaviorPassContext(
            metadata={
                'change_model': change_model,
                'repository_model': repository_model,
            }
        )

        # Execute each pass in sequence
        for compiler_pass in self.passes:
            context = compiler_pass.run(context)

        # Create and return the behavior model
        return self._build_behavior_model(context)

    def _build_behavior_model(self, context: BehaviorPassContext) -> BehaviorModel:
        """
        Build the final BehaviorModel from the pass context.

        Args:
            context: Final pass context with all behavior data

        Returns:
            Complete BehaviorModel
        """
        return BehaviorModel(
            behaviors=tuple(context.behaviors),
            execution_graphs=tuple(context.execution_graphs),
        )

    def get_pass_names(self) -> list[str]:
        """Get the names of all passes in execution order."""
        return [pass_.name for pass_ in self.passes]
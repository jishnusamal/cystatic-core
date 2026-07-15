"""Behavior compiler - orchestrates compilation passes."""

from typing import Any

from .passes import (
    BehaviorPassContext,
    BehaviorCompilationPass,
    BehaviorGraphPass,
    ExecutionChainPass,
    EntryPointPass,
    TerminalPointPass,
    SharedExecutionPass,
    ReachableUnitsPass,
)
from behavior.model import BehaviorModel
from change.model import RepositoryDelta
from language_adapters.model import RepositoryModel


class BehaviorCompiler:
    """
    Compiles a Change Model + Repository Delta into a Behavior Model.

    This is the main entry point for behavior compilation.
    It orchestrates the execution of all compilation passes in order.

    Input: ChangeModel + RepositoryDelta
    Output: BehaviorModel containing affected behaviors and execution graphs

    Uses the head repository for execution graph traversal, call graph,
    endpoints, persistence, events, and transactions.
    Uses the base repository only when reasoning about removed symbols.
    """

    def __init__(self):
        """Initialize the compiler with all passes."""
        self.passes = [
            BehaviorCompilationPass(),
            BehaviorGraphPass(),
            ExecutionChainPass(),
            EntryPointPass(),
            TerminalPointPass(),
            SharedExecutionPass(),
            ReachableUnitsPass(),
        ]

    def compile(
        self,
        change_model: Any,
        repository_delta: RepositoryDelta | None = None,
        repository_model: Any = None,
    ) -> BehaviorModel:
        """
        Compile changes into a Behavior Model.

        Args:
            change_model: ChangeModel
            repository_delta: RepositoryDelta containing both base and head models
            repository_model: RepositoryModel (deprecated, use repository_delta)

        Returns:
            BehaviorModel containing affected behaviors and execution graphs
        """
        # Support both old and new interface for backward compatibility
        # Check if repository_delta is actually a RepositoryModel (old interface)
        if repository_delta is not None and hasattr(repository_delta, 'head_model'):
            head_model = repository_delta.head_model
            base_model = repository_delta.base_model
        elif repository_delta is not None:
            # It's a RepositoryModel passed as the second argument
            head_model = repository_delta
            base_model = None
        else:
            head_model = repository_model
            base_model = None

        # Initialize pass context with models
        context = BehaviorPassContext(
            metadata={
                'change_model': change_model,
                'repository_model': head_model,
                'repository_delta': repository_delta,
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
        # Calculate max execution depth
        max_depth = 0
        for chain in context.execution_chains:
            chain_depth = chain.get_max_depth()
            if chain_depth > max_depth:
                max_depth = chain_depth

        return BehaviorModel(
            behaviors=tuple(context.behaviors),
            execution_graphs=tuple(context.execution_graphs),
            execution_chains=tuple(context.execution_chains),
            entry_points=tuple(context.entry_points),
            terminal_points=tuple(context.terminal_points),
            shared_executions=tuple(context.shared_executions),
            reachable_units=tuple(context.reachable_units),
            execution_depth=max_depth,
        )

    def get_pass_names(self) -> list[str]:
        """Get the names of all passes in execution order."""
        return [pass_.name for pass_ in self.passes]

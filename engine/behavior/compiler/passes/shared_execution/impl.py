"""Shared Execution Pass - identifies infrastructure shared across behaviors."""

from engine.behavior.model import SharedExecution

from ..base import BehaviorCompilerPass, BehaviorPassContext


class SharedExecutionPass(BehaviorCompilerPass):
    """
    Pass 6: Shared Execution

    Identify symbols that are used by multiple behaviors.
    These represent shared infrastructure.

    Input: Execution graphs from Pass 2
    Output: Shared executions for symbols used by multiple behaviors
    """

    @property
    def name(self) -> str:
        return "shared_execution"

    def run(self, context: BehaviorPassContext) -> BehaviorPassContext:
        """
        Execute shared execution pass.

        Args:
            context: Pass context with execution graphs

        Returns:
            Updated context with shared executions
        """
        if not context.execution_graphs:
            context.shared_executions = []
            return context

        # Build a map of symbol_id -> list of behavior_ids
        symbol_to_behaviors: dict[str, set[str]] = {}
        for graph in context.execution_graphs:
            for node in graph.nodes:
                if node.symbol_id not in symbol_to_behaviors:
                    symbol_to_behaviors[node.symbol_id] = set()
                symbol_to_behaviors[node.symbol_id].add(graph.behavior_id)

        # Find symbols used by multiple behaviors
        shared_executions = []
        for symbol_id, behavior_ids in symbol_to_behaviors.items():
            if len(behavior_ids) > 1:
                # This symbol is shared across multiple behaviors
                se = SharedExecution(
                    id=f"shared://{symbol_id}",
                    symbol_id=symbol_id,
                    used_by=tuple(sorted(behavior_ids)),
                )
                shared_executions.append(se)

        context.shared_executions = shared_executions
        return context

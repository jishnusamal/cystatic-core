"""Execution Chain Pass - builds ordered execution chains from execution graphs."""

from ..base import BehaviorCompilerPass, BehaviorPassContext
from behavior.model import ExecutionChain, ExecutionUnit, ExecutionGraph


class ExecutionChainPass(BehaviorCompilerPass):
    """
    Pass 3: Execution Chain

    For each behavior, build an ordered execution chain from the execution graph.
    This transforms the symbol-based graph into an execution-oriented chain.

    Input: Execution graphs from Pass 2
    Output: Execution chains for each behavior
    """

    @property
    def name(self) -> str:
        return "execution_chain"

    def run(self, context: BehaviorPassContext) -> BehaviorPassContext:
        """
        Execute execution chain pass.

        Args:
            context: Pass context with execution graphs

        Returns:
            Updated context with execution chains
        """
        if not context.behaviors or not context.execution_graphs:
            context.execution_chains = []
            return context

        # Build execution chain for each behavior
        execution_chains = []
        for behavior in context.behaviors:
            graph = context.get_execution_graph(behavior.id) if hasattr(context, 'get_execution_graph') else None
            # Find the graph for this behavior
            graph = None
            for g in context.execution_graphs:
                if g.behavior_id == behavior.id:
                    graph = g
                    break

            if graph is None:
                continue

            chain = self._build_execution_chain(behavior, graph)
            execution_chains.append(chain)

        context.execution_chains = execution_chains
        return context

    def _build_execution_chain(
        self,
        behavior,
        graph: ExecutionGraph,
    ) -> ExecutionChain:
        """
        Build an execution chain from an execution graph.

        This creates ordered execution units from the graph nodes.

        Args:
            behavior: The Behavior
            graph: The ExecutionGraph

        Returns:
            An ExecutionChain
        """
        # Create execution units from graph nodes, sorted by order
        units = []
        for node in sorted(graph.nodes, key=lambda n: n.order):
            unit = ExecutionUnit(
                id=f"unit://{behavior.id}#{node.symbol_id}",
                name=self._derive_unit_name(node.symbol_id),
                symbol_id=node.symbol_id,
                order=node.order,
                evidence=node.evidence,
            )
            units.append(unit)

        return ExecutionChain(
            id=f"chain://{behavior.id}",
            behavior_id=behavior.id,
            units=tuple(units),
            evidence=graph.evidence,
        )

    @staticmethod
    def _derive_unit_name(symbol_id: str) -> str:
        """
        Derive a human-readable name from a symbol id.

        Args:
            symbol_id: The symbol id

        Returns:
            A human-readable name
        """
        # Extract the symbol name from the id
        # Format: <language>://<path>#<name> or <language>://<path>::<name>
        if "://" in symbol_id:
            rest = symbol_id.split("://", 1)[1]
        else:
            rest = symbol_id

        name = rest.split("#")[-1].split("::")[-1]
        return name.replace("_", " ").title()
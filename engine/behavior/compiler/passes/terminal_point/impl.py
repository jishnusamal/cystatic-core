"""Terminal Point Pass - identifies where execution ends."""

from ..base import BehaviorCompilerPass, BehaviorPassContext
from engine.behavior.model import TerminalPoint, ExecutionGraph


class TerminalPointPass(BehaviorCompilerPass):
    """
    Pass 5: Terminal Point

    For each behavior, identify terminal points in the execution graph.
    A terminal point is a symbol that does not call any other symbols
    within the execution graph.

    Input: Execution graphs from Pass 2
    Output: Terminal points for each behavior
    """

    @property
    def name(self) -> str:
        return "terminal_point"

    def run(self, context: BehaviorPassContext) -> BehaviorPassContext:
        """
        Execute terminal point pass.

        Args:
            context: Pass context with execution graphs

        Returns:
            Updated context with terminal points
        """
        if not context.behaviors or not context.execution_graphs:
            context.terminal_points = []
            return context

        terminal_points = []
        for graph in context.execution_graphs:
            tps = self._find_terminal_points(graph)
            terminal_points.extend(tps)

        context.terminal_points = terminal_points
        return context

    def _find_terminal_points(self, graph: ExecutionGraph) -> list[TerminalPoint]:
        """
        Find terminal points in an execution graph.

        A terminal point is a node that has no outgoing edges.

        Args:
            graph: The ExecutionGraph

        Returns:
            List of TerminalPoint objects
        """
        # Get all symbol IDs that are called (callees)
        called_symbols = {edge.callee_id for edge in graph.edges}

        # Find nodes that are not callers (no outgoing edges)
        terminal_nodes = [
            node for node in graph.nodes
            if node.symbol_id not in called_symbols
        ]

        # If no terminal points found, use the last node in order
        if not terminal_nodes and graph.nodes:
            last_node = max(graph.nodes, key=lambda n: n.order)
            terminal_nodes = [last_node]

        terminal_points = []
        for node in terminal_nodes:
            tp = TerminalPoint(
                id=f"terminal://{graph.behavior_id}#{node.symbol_id}",
                behavior_id=graph.behavior_id,
                symbol_id=node.symbol_id,
                kind="return",
                evidence=node.evidence,
            )
            terminal_points.append(tp)

        return terminal_points
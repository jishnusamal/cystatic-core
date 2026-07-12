"""Behavior Graph Pass - builds execution graphs for each behavior."""

from collections import deque

from ..base import BehaviorCompilerPass, BehaviorPassContext
from behavior.model import ExecutionGraph, ExecutionNode, ExecutionEdge


class BehaviorGraphPass(BehaviorCompilerPass):
    """
    Pass 2: Behavior Graph

    For each discovered behavior, build a bounded execution graph by
    projecting the repository-wide call graph onto the behavior's symbol tree.

    Input: Discovered behaviors from Pass 1, RepositoryModel
    Output: Execution graphs for each behavior
    """

    @property
    def name(self) -> str:
        return "behavior_graph"

    def run(self, context: BehaviorPassContext) -> BehaviorPassContext:
        """
        Execute behavior graph pass.

        Args:
            context: Pass context with behaviors and repository model

        Returns:
            Updated context with execution graphs
        """
        repository_model = context.metadata.get('repository_model')

        if not context.behaviors or not repository_model:
            context.execution_graphs = []
            return context

        # Build execution graph for each behavior
        execution_graphs = []
        for behavior in context.behaviors:
            graph = self._build_execution_graph(behavior, repository_model)
            execution_graphs.append(graph)

        context.execution_graphs = execution_graphs
        return context

    def _build_execution_graph(
        self,
        behavior,
        repository_model,
    ) -> ExecutionGraph:
        """
        Build an execution graph for a single behavior.

        This performs a BFS/DFS from the behavior root symbol through
        the repository call graph, collecting only reachable symbols.

        Args:
            behavior: The Behavior to build a graph for
            repository_model: The RepositoryModel with the call graph

        Returns:
            An ExecutionGraph for this behavior
        """
        root_symbol_id = behavior.root_symbol_id

        # Traverse call graph from the root symbol downward
        visited_nodes: dict[str, int] = {}  # symbol_id -> order
        collected_edges: list[ExecutionEdge] = []
        order_counter = 0

        queue: deque[str] = deque([root_symbol_id])

        while queue:
            current_id = queue.popleft()

            if current_id in visited_nodes:
                continue

            # Assign execution order
            visited_nodes[current_id] = order_counter
            order_counter += 1

            # Get outgoing calls from this symbol
            calls = repository_model.get_calls_for(current_id)
            for edge in calls:
                # Only follow direct calls in the execution graph
                if edge.callee_id not in visited_nodes:
                    queue.append(edge.callee_id)

                # Collect the edge
                collected_edges.append(ExecutionEdge(
                    caller_id=edge.caller_id,
                    callee_id=edge.callee_id,
                    call_type=edge.call_type,
                ))

        # Create execution nodes sorted by order
        sorted_symbols = sorted(visited_nodes.items(), key=lambda x: x[1])
        execution_nodes = tuple(
            ExecutionNode(
                symbol_id=symbol_id,
                order=order,
            )
            for symbol_id, order in sorted_symbols
        )

        return ExecutionGraph(
            behavior_id=behavior.id,
            nodes=execution_nodes,
            edges=tuple(collected_edges),
        )
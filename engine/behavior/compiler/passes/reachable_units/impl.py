"""Reachable Units Pass - identifies execution units reachable from changed symbols."""

from engine.behavior.model import ExecutionGraph, ExecutionUnit

from ..base import BehaviorCompilerPass, BehaviorPassContext


class ReachableUnitsPass(BehaviorCompilerPass):
    """
    Pass 7: Reachable Units

    For each behavior, identify which execution units are reachable from
    the changed symbols. This helps understand the scope of impact.

    Input: Execution graphs and behaviors from Pass 1 and 2
    Output: Reachable execution units for each behavior
    """

    @property
    def name(self) -> str:
        return "reachable_units"

    def run(self, context: BehaviorPassContext) -> BehaviorPassContext:
        """
        Execute reachable units pass.

        Args:
            context: Pass context with execution graphs and behaviors

        Returns:
            Updated context with reachable units
        """
        if not context.behaviors or not context.execution_graphs:
            context.reachable_units = []
            return context

        reachable_units = []
        for behavior in context.behaviors:
            # Find the graph for this behavior
            graph = None
            for g in context.execution_graphs:
                if g.behavior_id == behavior.id:
                    graph = g
                    break

            if graph is None:
                continue

            # Get changed symbol IDs for this behavior
            changed_ids = set(behavior.changed_symbol_ids)

            # Find all reachable units from changed symbols
            units = self._find_reachable_units(graph, changed_ids, behavior.id)
            reachable_units.extend(units)

        context.reachable_units = reachable_units
        return context

    def _find_reachable_units(
        self,
        graph: ExecutionGraph,
        changed_ids: set[str],
        behavior_id: str,
    ) -> list[ExecutionUnit]:
        """
        Find execution units reachable from changed symbols.

        Args:
            graph: The ExecutionGraph
            changed_ids: Set of changed symbol IDs
            behavior_id: The behavior ID

        Returns:
            List of reachable ExecutionUnit objects
        """
        # Build adjacency: caller -> list of callees
        callees_of: dict[str, list[str]] = {}
        for edge in graph.edges:
            if edge.caller_id not in callees_of:
                callees_of[edge.caller_id] = []
            callees_of[edge.caller_id].append(edge.callee_id)

        # BFS from changed symbols
        reachable: set[str] = set()
        queue = list(changed_ids)

        while queue:
            current = queue.pop(0)
            if current in reachable:
                continue
            reachable.add(current)

            # Add callees
            for callee in callees_of.get(current, []):
                if callee not in reachable:
                    queue.append(callee)

        # Create execution units for reachable symbols
        units = []
        for node in graph.nodes:
            if node.symbol_id in reachable:
                unit = ExecutionUnit(
                    id=f"reachable://{behavior_id}#{node.symbol_id}",
                    name=self._derive_unit_name(node.symbol_id),
                    symbol_id=node.symbol_id,
                    order=node.order,
                    evidence=node.evidence,
                )
                units.append(unit)

        return units

    @staticmethod
    def _derive_unit_name(symbol_id: str) -> str:
        """
        Derive a human-readable name from a symbol id.

        Args:
            symbol_id: The symbol id

        Returns:
            A human-readable name
        """
        if "://" in symbol_id:
            rest = symbol_id.split("://", 1)[1]
        else:
            rest = symbol_id

        name = rest.split("#")[-1].split("::")[-1]
        return name.replace("_", " ").title()

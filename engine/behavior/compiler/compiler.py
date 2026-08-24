"""Behavior compiler - orchestrates compilation passes."""

from typing import Any

from engine.behavior.model import BehaviorModel
from engine.change.model import RepositoryDelta
from engine.repository.model import RepositoryModel

from .impact_engine import ImpactEngine
from .passes import (
    BehaviorCompilationPass,
    BehaviorGraphPass,
    BehaviorPassContext,
    EntryPointPass,
    ExecutionChainPass,
    ReachableUnitsPass,
    SharedExecutionPass,
    TerminalPointPass,
)


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
        repository_delta: RepositoryDelta | RepositoryModel | None = None,
        repository_model: Any = None,
        repository_query: Any = None,
        capabilities: Any = None,
    ) -> BehaviorModel:
        """
        Compile changes into a Behavior Model.

        Args:
            change_model: ChangeModel
            repository_delta: RepositoryDelta containing both base and head models, or RepositoryModel (deprecated)
            repository_model: RepositoryModel (deprecated, use repository_delta)
            repository_query: Query interface
            capabilities: Language capabilities metadata (passed dynamically to preserve language boundary)

        Returns:
            BehaviorModel containing affected behaviors and execution graphs
        """
        # Support both old and new interface for backward compatibility
        # Check if repository_delta is actually a RepositoryDelta (new interface)
        if (
            repository_delta is not None
            and hasattr(repository_delta, "head_model")
            and hasattr(repository_delta, "base_model")
        ):
            head_model = repository_delta.head_model
        elif repository_delta is not None:
            # It's a RepositoryModel passed as repository_delta (deprecated usage)
            head_model = repository_delta
        else:
            head_model = repository_model

        if repository_query is None and head_model is not None:
            from engine.change.compiler.compiler import RepositoryModelQuery

            repository_query = RepositoryModelQuery(head_model)

        # Calculate impact surface using bounded traversal
        impact_engine = ImpactEngine()
        changed_ids = set()
        for s in getattr(change_model, "added_symbols", ()):
            changed_ids.add(s.id)
        for s in getattr(change_model, "removed_symbols", ()):
            changed_ids.add(s.id)
        for m in getattr(change_model, "modified_symbols", ()):
            changed_ids.add(m.symbol.id)

        impact_surface = None
        if repository_query is not None:
            if capabilities is not None and not getattr(capabilities, "calls", True):
                # Bypassing call graph traversal when calls capability is False
                from engine.behavior.model.impact_surface import ImpactSurface
                affected_symbols = set(changed_ids)
                affected_endpoints = set()
                affected_databases = set()
                affected_events = set()

                all_entry_points = repository_query.get_entry_points() if getattr(capabilities, "entrypoints", True) else ()
                entry_point_map = {str(ep.handler_id): ep for ep in all_entry_points}
                for current_id in changed_ids:
                    if current_id in entry_point_map:
                        affected_endpoints.add(entry_point_map[current_id])
                    if getattr(capabilities, "persistence", True):
                        dbs = repository_query.get_database_relationships(current_id)
                        for db in dbs:
                            affected_databases.add(db)
                    if getattr(capabilities, "events", True):
                        events = repository_query.get_published_events(current_id)
                        for ev in events:
                            affected_events.add(ev)

                impact_surface = ImpactSurface(
                    affected_symbols=frozenset(affected_symbols),
                    affected_endpoints=frozenset(affected_endpoints),
                    affected_databases=frozenset(affected_databases),
                    affected_events=frozenset(affected_events),
                )
            else:
                impact_surface = impact_engine.calculate_impact(
                    changed_ids, repository_query, capabilities
                )

        # Phase 8: We no longer run the legacy passes that depend on the materialized graph.
        # Instead, we return the ImpactSurface produced by bounded traversal.
        return impact_surface

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
            max_depth = max(max_depth, chain_depth)

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

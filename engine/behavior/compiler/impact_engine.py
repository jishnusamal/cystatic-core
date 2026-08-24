"""Impact Engine - calculates impact surfaces using bounded traversal over RepositoryQuery."""

from collections import deque
from dataclasses import dataclass
from typing import Any, cast

from engine.behavior.model.impact_surface import ImpactSurface
from engine.repository.query import SymbolId
from engine.repository.query.repository import RepositoryQuery


@dataclass
class TraversalConfig:
    """Configuration for bounded traversal."""

    max_depth: int = 15
    max_visited: int = 50000


class ImpactEngine:
    """
    Engine to trace the impact of code changes.

    Performs bounded graph traversal using the RepositoryQuery interface,
    without requiring the full RepositoryModel to be materialized in memory.
    """

    def __init__(self, config: TraversalConfig | None = None):
        self.config = config or TraversalConfig()

    def calculate_impact(
        self,
        changed_symbol_ids: set[str],
        repository_query: RepositoryQuery,
        capabilities: Any = None,
    ) -> ImpactSurface:
        """
        Calculate the impact surface originating from changed symbols.

        Uses bounded traversal to limit memory consumption.
        """
        if not changed_symbol_ids:
            return ImpactSurface()

        visited_up: set[str] = set()
        visited_down: set[str] = set()

        queue_up: deque[tuple[str, int]] = deque((str(sid), 0) for sid in changed_symbol_ids)
        queue_down: deque[tuple[str, int]] = deque(
            (str(sid), 0) for sid in changed_symbol_ids
        )

        affected_symbols: set[str] = {str(sid) for sid in changed_symbol_ids}

        # We need to map symbol_id -> EntryPoint (if they are an entry point)
        # However, RepositoryQuery.get_entry_points() gives us all of them.
        all_entry_points = repository_query.get_entry_points() if (capabilities is None or getattr(capabilities, "entrypoints", True)) else ()
        entry_point_map = {str(ep.handler_id): ep for ep in all_entry_points}

        affected_endpoints = set()
        affected_databases = set()
        affected_events = set()

        # 1. Traverse Up (Find callers / Entry Points)
        while queue_up and len(visited_up) < self.config.max_visited:
            current_id, depth = queue_up.popleft()

            if current_id in visited_up:
                continue
            visited_up.add(current_id)
            affected_symbols.add(current_id)

            # Check if this symbol is an entry point
            if current_id in entry_point_map:
                affected_endpoints.add(entry_point_map[current_id])

            if depth >= self.config.max_depth:
                continue

            # Fetch callers via repository query
            # get_callers returns calls targeting current_id (i.e. caller calls current_id)
            callers = repository_query.get_callers(cast(SymbolId, current_id))
            for call in callers:
                caller_id_str = str(call.caller_id)
                if caller_id_str not in visited_up:
                    queue_up.append((caller_id_str, depth + 1))

        # 2. Traverse Down (Find endpoints / databases / events)
        while queue_down and len(visited_down) < self.config.max_visited:
            current_id, depth = queue_down.popleft()

            if current_id in visited_down:
                continue
            visited_down.add(current_id)
            affected_symbols.add(current_id)

            # Check database dependencies and events
            if capabilities is None or getattr(capabilities, "persistence", True):
                dbs = repository_query.get_database_relationships(
                    cast(SymbolId, current_id)
                )
                for db in dbs:
                    affected_databases.add(db)

            if capabilities is None or getattr(capabilities, "events", True):
                events = repository_query.get_published_events(
                    cast(SymbolId, current_id)
                )
                for ev in events:
                    affected_events.add(ev)

            if depth >= self.config.max_depth:
                continue

            # Fetch callees
            callees = repository_query.get_callees(cast(SymbolId, current_id))
            for call in callees:
                callee_id_str = str(call.callee_id)
                if callee_id_str not in visited_down:
                    queue_down.append((callee_id_str, depth + 1))

        return ImpactSurface(
            affected_symbols=frozenset(affected_symbols),
            affected_endpoints=frozenset(affected_endpoints),
            affected_databases=frozenset(affected_databases),
            affected_events=frozenset(affected_events),
        )

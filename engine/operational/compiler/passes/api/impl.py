"""API Compilation Pass - compiles externally visible interface information.

Question: Which externally visible interfaces are affected?

Produces APIModel with:
- REST: REST endpoints affected
- GraphQL: GraphQL resolvers/mutations affected
- RPC: RPC endpoints affected
- CLI: CLI commands affected
- Cron: Scheduled jobs affected
- Workers: Background workers affected

This is the public operational surface.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, cast

from engine.operational.compiler.passes.base import (
    OperationalCompilerPass,
    OperationalPassContext,
)
from engine.repository.model import EntryPoint, EntryPointKind, RepositoryModel, Symbol
from engine.operational.model import OperationalChangeModel


@dataclass(frozen=True)
class APIModel:
    """
    Externally visible interface information for affected behaviors.

    All fields are deterministically derived from the repository model.
    """

    # REST endpoints affected: (method, route, handler_symbol_id)
    rest: tuple[tuple[str, str, str], ...] = field(default_factory=tuple)

    # GraphQL resolvers/mutations affected: (type, field_name, resolver_symbol_id)
    graphql: tuple[tuple[str, str, str], ...] = field(default_factory=tuple)

    # RPC endpoints affected: (service, method, handler_symbol_id)
    rpc: tuple[tuple[str, str, str], ...] = field(default_factory=tuple)

    # CLI commands affected: (command_name, handler_symbol_id)
    cli: tuple[tuple[str, str], ...] = field(default_factory=tuple)

    # Cron/scheduled jobs affected: (schedule, job_name, handler_symbol_id)
    cron: tuple[tuple[str, str, str], ...] = field(default_factory=tuple)

    # Worker entry points affected: (worker_name, handler_symbol_id)
    workers: tuple[tuple[str, str], ...] = field(default_factory=tuple)

    def __post_init__(self):
        """Convert mutable defaults to immutable types."""
        for attr in ("rest", "graphql", "rpc", "cli", "cron", "workers"):
            val = getattr(self, attr)
            if isinstance(val, list):
                object.__setattr__(self, attr, tuple(val))


# GraphQL patterns
_GRAPHQL_TYPE_PATTERNS = {
    "query", "mutation", "subscription", "resolver",
}


class APICompilationPass(OperationalCompilerPass):
    """
    Pass 4 of Operational compilation.

    Compiles externally visible interfaces affected by the change.
    """

    @property
    def name(self) -> str:
        return "api_compilation"

    def validate_input(self, context: OperationalPassContext) -> bool:
        """Verify the composed model exists."""
        return context.composed_model is not None

    def run(self, context: OperationalPassContext) -> OperationalPassContext:
        """
        Execute API compilation on the composed model.

        Args:
            context: Pass context with composed_model set.

        Returns:
            Updated context with API model set on composed_model.
        """
        if not self.validate_input(context):
            return context

        model = context.composed_model
        if model is None:
            return context
        
        repo = model.repository

        # Use cached values from context
        affected_symbol_ids = context.get_affected_symbol_ids()
        symbol_map = context.get_symbol_map()
        callers_of = context.get_callers_of()

        # Build reverse reachability: find all symbols that can reach an affected symbol
        # within 50 hops in the call graph (equivalent to traversing reverse call graph)
        from collections import deque
        can_reach_affected: set[str] = set(affected_symbol_ids)
        queue: deque[tuple[str, int]] = deque((sid, 0) for sid in affected_symbol_ids)
        visited_reverse: set[str] = set(affected_symbol_ids)

        while queue:
            current, depth = queue.popleft()
            if depth >= 50:
                continue
            for caller in callers_of.get(current, []):
                if caller not in visited_reverse:
                    visited_reverse.add(caller)
                    can_reach_affected.add(caller)
                    queue.append((caller, depth + 1))

        # Classify entry points by kind
        rest_endpoints: list[tuple[str, str, str]] = []
        graphql_endpoints: list[tuple[str, str, str]] = []
        rpc_endpoints: list[tuple[str, str, str]] = []
        cli_commands: list[tuple[str, str]] = []
        cron_jobs: list[tuple[str, str, str]] = []
        worker_entries: list[tuple[str, str]] = []

        for ep in repo.entry_points:
            # Check if this entry point's handler is affected or can reach an affected symbol
            handler_affected = ep.handler_id in affected_symbol_ids
            handler_reachable = ep.handler_id in can_reach_affected

            if not handler_affected and not handler_reachable:
                continue

            route = ep.route

            if ep.kind == EntryPointKind.REST_ENDPOINT:
                # Parse method and route from the route string
                # e.g., "POST /checkout" -> ("POST", "/checkout")
                parts = route.split(" ", 1)
                method = parts[0] if len(parts) > 1 else "GET"
                path = parts[1] if len(parts) > 1 else route
                rest_endpoints.append((method, path, ep.handler_id))

            elif ep.kind == EntryPointKind.GRAPHQL_RESOLVER:
                # Infer GraphQL type from metadata or route
                gql_type = ep.metadata.get("graphql_type", "query")
                field_name = route.split("/")[-1] if "/" in route else route
                graphql_endpoints.append((gql_type, field_name, ep.handler_id))

            elif ep.kind == EntryPointKind.RPC_HANDLER:
                parts = route.split("/", 1)
                service = parts[0] if len(parts) > 1 else "default"
                method = parts[1] if len(parts) > 1 else route
                rpc_endpoints.append((service, method, ep.handler_id))

            elif ep.kind == EntryPointKind.CLI_COMMAND:
                cli_commands.append((route, ep.handler_id))

            elif ep.kind == EntryPointKind.SCHEDULED_JOB:
                schedule = ep.metadata.get("schedule", "unknown")
                job_name = route
                cron_jobs.append((schedule, job_name, ep.handler_id))

            elif ep.kind == EntryPointKind.WORKER_ENTRY:
                worker_name = ep.metadata.get("worker_name", route)
                worker_entries.append((worker_name, ep.handler_id))

        # Also check changed endpoints from the change model
        change = model.change
        for changed_ep in change.changed_endpoints:
            parts = []
            if changed_ep.old_endpoint:
                parts.append(changed_ep.old_endpoint)
            if changed_ep.new_endpoint:
                parts.append(changed_ep.new_endpoint)
            for endpoint in parts:
                method, path = "GET", endpoint
                if " " in endpoint:
                    method, path = endpoint.split(" ", 1)
                rest_endpoints.append((method, path, changed_ep.symbol_id))

        # Detect additional GraphQL resolvers from changed symbols
        for sid in affected_symbol_ids:
            sym = symbol_map.get(sid)
            if sym is None:
                continue
            props = sym.properties
            if props.get("graphql_type") or props.get("resolver_for"):
                gql_type = props.get("graphql_type", "query")
                field_name = props.get("resolver_for", sym.name)
                graphql_endpoints.append((gql_type, field_name, sid))

        api_model = APIModel(
            rest=tuple(sorted(set(rest_endpoints))),
            graphql=tuple(sorted(set(graphql_endpoints))),
            rpc=tuple(sorted(set(rpc_endpoints))),
            cli=tuple(sorted(set(cli_commands))),
            cron=tuple(sorted(set(cron_jobs))),
            workers=tuple(sorted(set(worker_entries))),
        )

        # Enrich the composed model
        context.composed_model = model.__class__(
            repository=model.repository,
            change=model.change,
            behavior=model.behavior,
            dependency=model.dependency,
            data=model.data,
            event=model.event,
            validation=model.validation,
            api=api_model,
            metrics=model.metrics if hasattr(model, 'metrics') else None,
        )

        return context

    @staticmethod
    def _is_reachable_to_affected(
        repo: RepositoryModel,
        start_id: str,
        affected_ids: set[str],
    ) -> bool:
        """
        Check if any affected symbol is reachable from start_id via the call graph.

        Deprecated: Use reverse reachability set instead.
        """
        if start_id in affected_ids:
            return True

        from collections import deque
        adj: dict[str, list[str]] = {}
        for edge in repo.call_graph.edges:
            if edge.caller_id not in adj:
                adj[edge.caller_id] = []
            adj[edge.caller_id].append(edge.callee_id)

        visited: set[str] = set()
        queue: deque[str] = deque([start_id])
        depth = 0
        max_depth = 50  # Safety limit

        while queue and depth < max_depth:
            level_size = len(queue)
            for _ in range(level_size):
                current = queue.popleft()
                if current in visited:
                    continue
                visited.add(current)
                if current in affected_ids:
                    return True
                for neighbor in adj.get(current, []):
                    if neighbor not in visited:
                        queue.append(neighbor)
            depth += 1

        return False
"""Dependency Compilation Pass - compiles structural dependency information.

Question: What structural dependencies does the change have?

Produces DependencyModel with:
- Callers: symbols that invoke affected symbols
- Dependents: symbols that affected symbols invoke
- Shared Modules: modules shared across the dependency boundary
- Cross-Service References: call edges crossing service boundaries
- Fan-In / Fan-Out: per-symbol caller/callee counts
- Dependency Depth: maximum call-graph traversal depth

Everything is directly traceable to repository evidence. No inference.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from engine.operational.compiler.passes.base import (
    OperationalCompilerPass,
    OperationalPassContext,
)
from engine.repository.model import Symbol


@dataclass(frozen=True)
class DependencyModel:
    """
    Structural dependency information for affected symbols.

    All fields are deterministically derived from the repository call graph
    and the set of affected symbols. No speculation.
    """

    # Symbols that invoke at least one affected symbol
    callers: tuple[Symbol, ...] = field(default_factory=tuple)

    # Symbols that affected symbols invoke
    dependents: tuple[Symbol, ...] = field(default_factory=tuple)

    # Module paths shared across the dependency boundary
    shared_modules: tuple[str, ...] = field(default_factory=tuple)

    # Cross-service call edges: (caller_symbol_id, callee_symbol_id, service_boundary)
    cross_service_references: tuple[tuple[str, str, str], ...] = field(
        default_factory=tuple
    )

    # Per-symbol fan-in: symbol_id -> number of distinct callers
    fan_in: dict[str, int] = field(default_factory=dict)

    # Per-symbol fan-out: symbol_id -> number of distinct callees
    fan_out: dict[str, int] = field(default_factory=dict)

    # Maximum call-graph traversal depth from affected symbols
    dependency_depth: int = 0

    def __post_init__(self):
        """Convert mutable defaults to immutable types."""
        if isinstance(self.callers, list):
            object.__setattr__(self, "callers", tuple(self.callers))
        if isinstance(self.dependents, list):
            object.__setattr__(self, "dependents", tuple(self.dependents))
        if isinstance(self.shared_modules, list):
            object.__setattr__(self, "shared_modules", tuple(self.shared_modules))
        if isinstance(self.cross_service_references, list):
            object.__setattr__(
                self, "cross_service_references", tuple(self.cross_service_references)
            )
        if isinstance(self.fan_in, dict):
            object.__setattr__(self, "fan_in", dict(self.fan_in))
        if isinstance(self.fan_out, dict):
            object.__setattr__(self, "fan_out", dict(self.fan_out))


def _service_of(symbol_id: Any) -> str:
    """Extract the top-level service/module from a symbol id.

    Symbol ids are formatted as ``<language>://<path>#<name>`` or
    ``<language>://<path>::<name>``. The service is the first path segment.
    """
    symbol_id_str = str(symbol_id)
    if "://" in symbol_id_str:
        rest = symbol_id_str.split("://", 1)[1]
    else:
        rest = symbol_id_str
    path = rest.split("#", 1)[0].split("::", 1)[0]
    parts = path.split("/", 1)
    return parts[0] if parts else path


class DependencyCompilationPass(OperationalCompilerPass):
    """
    Pass 3 of Operational compilation.

    Compiles structural dependencies of the change from the repository call
    graph and the set of affected symbols.
    """

    @property
    def name(self) -> str:
        return "dependency_compilation"

    def validate_input(self, context: OperationalPassContext) -> bool:
        """Verify the composed model exists."""
        return context.composed_model is not None

    def run(self, context: OperationalPassContext) -> OperationalPassContext:
        """
        Execute dependency compilation on the composed model.

        Args:
            context: Pass context with composed_model set.

        Returns:
            Updated context with dependency model set on composed_model.
        """
        if not self.validate_input(context):
            return context

        model = context.composed_model
        if model is None:
            return context

        repo = model.repository

        # Collect all affected symbol IDs and maps using cached context methods
        affected_symbol_ids = context.get_affected_symbol_ids()
        symbol_map = context.get_symbol_map()
        callees_of = context.get_callees_of()
        callers_of = context.get_callers_of()

        # Callers: symbols that invoke an affected symbol
        caller_ids: set[str] = set()
        for sid in affected_symbol_ids:
            caller_ids.update(callers_of.get(sid, []))

        # Dependents: symbols that affected symbols invoke
        dependent_ids: set[str] = set()
        for sid in affected_symbol_ids:
            dependent_ids.update(callees_of.get(sid, []))

        # Fan-in / fan-out per affected symbol
        fan_in: dict[str, int] = {
            sid: len(set(callers_of.get(sid, []))) for sid in affected_symbol_ids
        }
        fan_out: dict[str, int] = {
            sid: len(set(callees_of.get(sid, []))) for sid in affected_symbol_ids
        }

        # Helper to safely get file path from Symbol fact or legacy Symbol model
        repo = model.repository
        def get_symbol_file_path(s: Symbol) -> str:
            if hasattr(s, "file") and s.file:
                return s.file
            if hasattr(s, "file_id") and s.file_id is not None:
                if hasattr(repo, "get_file"):
                    f = repo.get_file(s.file_id)
                    if f is not None:
                        return f.path
                if isinstance(s.file_id, str):
                    return s.file_id
            return ""

        # Shared modules: modules referenced by both callers and dependents
        caller_modules = {get_symbol_file_path(symbol_map[c]) for c in caller_ids if c in symbol_map}
        dependent_modules = {
            get_symbol_file_path(symbol_map[d]) for d in dependent_ids if d in symbol_map
        }
        shared_modules = tuple(sorted(caller_modules & dependent_modules))

        # Cross-service references: call edges crossing a service boundary
        cross_service: set[tuple[str, str, str]] = set()
        if hasattr(repo, "call_graph") and repo.call_graph is not None:
            for edge in repo.call_graph.edges:
                caller_svc = _service_of(edge.caller_id)
                callee_svc = _service_of(edge.callee_id)
                if caller_svc != callee_svc:
                    cross_service.add(
                        (edge.caller_id, edge.callee_id, f"{caller_svc}->{callee_svc}")
                    )
        elif hasattr(repo, "get_callees"):
            for sid in affected_symbol_ids:
                for call in repo.get_callees(sid):
                    caller_svc = _service_of(call.caller_id)
                    callee_svc = _service_of(call.callee_id)
                    if caller_svc != callee_svc:
                        cross_service.add(
                            (
                                call.caller_id,
                                call.callee_id,
                                f"{caller_svc}->{callee_svc}",
                            )
                        )

        # Dependency depth: max BFS depth from affected symbols outward
        dependency_depth = self._compute_depth(callees_of, affected_symbol_ids)

        dependency_model = DependencyModel(
            callers=tuple(
                sorted(
                    (symbol_map[c] for c in caller_ids if c in symbol_map),
                    key=lambda s: s.id,
                )
            ),
            dependents=tuple(
                sorted(
                    (symbol_map[d] for d in dependent_ids if d in symbol_map),
                    key=lambda s: s.id,
                )
            ),
            shared_modules=shared_modules,
            cross_service_references=tuple(sorted(cross_service)),
            fan_in=fan_in,
            fan_out=fan_out,
            dependency_depth=dependency_depth,
        )

        # Enrich the composed model
        context.composed_model = model.__class__(
            repository=model.repository,
            change=model.change,
            behavior=model.behavior,
            dependency=dependency_model,
            data=model.data,
            event=model.event,
            validation=model.validation,
            api=model.api if hasattr(model, "api") else None,
            metrics=model.metrics if hasattr(model, "metrics") else None,
        )

        return context

    @staticmethod
    def _compute_depth(
        callees_of: dict[str, list[str]],
        seed_ids: set[str],
    ) -> int:
        """Compute the maximum call-graph traversal depth from seed symbols."""
        if not seed_ids:
            return 0

        from collections import deque

        visited: set[str] = set()
        queue: deque[tuple[str, int]] = deque((sid, 0) for sid in seed_ids)
        max_depth = 0

        while queue:
            current, depth = queue.popleft()
            if current in visited:
                continue
            visited.add(current)
            max_depth = max(max_depth, depth)
            for neighbor in callees_of.get(current, []):
                if neighbor not in visited:
                    queue.append((neighbor, depth + 1))

        return max_depth

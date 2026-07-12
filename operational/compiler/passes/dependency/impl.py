"""Pass 1 — Dependency Analysis.

Question: What depends on the affected behaviors?

Produces DependencyModel with:
- Callers: symbols that call into affected behaviors
- Dependents: symbols that depend on changed symbols
- Shared Modules: modules shared between affected and unaffected code
- Cross-service References: references across service boundaries
- Fan-in: number of callers per affected symbol
- Fan-out: number of callees per affected symbol
- Dependency Depth: maximum call depth from entry points

No impact assessment. Only structural dependency.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import FrozenSet

from operational.compiler.passes.base import (
    OperationalCompilerPass,
    OperationalPassContext,
)
from language_adapters.model import CallEdge, Symbol


@dataclass(frozen=True)
class DependencyModel:
    """
    Structural dependency information for affected behaviors.

    All fields are deterministically derived from the repository model.
    No speculation, no impact assessment.
    """

    # Symbols that call into affected behavior entry points
    callers: tuple[Symbol, ...] = field(default_factory=tuple)

    # Symbols that depend on changed symbols (imports, references, etc.)
    dependents: tuple[Symbol, ...] = field(default_factory=tuple)

    # Module paths shared between affected and unaffected code
    shared_modules: tuple[str, ...] = field(default_factory=tuple)

    # Cross-service references: (source_service, target_service, symbol_id)
    cross_service_references: tuple[tuple[str, str, str], ...] = field(default_factory=tuple)

    # Fan-in: number of callers per affected symbol id
    fan_in: dict[str, int] = field(default_factory=dict)

    # Fan-out: number of callees per affected symbol id
    fan_out: dict[str, int] = field(default_factory=dict)

    # Maximum call depth from entry points to changed symbols
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
            object.__setattr__(self, "cross_service_references", tuple(self.cross_service_references))
        if isinstance(self.fan_in, dict):
            object.__setattr__(self, "fan_in", dict(self.fan_in))
        if isinstance(self.fan_out, dict):
            object.__setattr__(self, "fan_out", dict(self.fan_out))


class DependencyAnalysisPass(OperationalCompilerPass):
    """
    Pass 1 of Operational Analysis compilation.

    Analyzes structural dependencies of affected behaviors.
    """

    @property
    def name(self) -> str:
        return "dependency_analysis"

    def validate_input(self, context: OperationalPassContext) -> bool:
        """Verify the composed model exists."""
        return context.composed_model is not None

    def run(self, context: OperationalPassContext) -> OperationalPassContext:
        """
        Execute dependency analysis on the composed model.

        Args:
            context: Pass context with composed_model set.

        Returns:
            Updated context with dependency model set on composed_model.
        """
        if not self.validate_input(context):
            return context

        model = context.composed_model
        repo = model.repository
        behavior = model.behavior
        change = model.change

        # Collect all affected symbol IDs from behaviors
        affected_symbol_ids: set[str] = set()
        for b in behavior.behaviors:
            affected_symbol_ids.add(b.root_symbol_id)
            affected_symbol_ids.update(b.changed_symbol_ids)

        # Also include all changed symbols from the change model
        for s in change.added_symbols:
            affected_symbol_ids.add(s.id)
        for s in change.removed_symbols:
            affected_symbol_ids.add(s.id)
        for ms in change.modified_symbols:
            affected_symbol_ids.add(ms.symbol.id)

        # Build symbol lookup
        symbol_map: dict[str, Symbol] = {s.id: s for s in repo.symbols}

        # 1. Callers: symbols that call into affected symbols
        callers: set[Symbol] = set()
        for edge in repo.call_graph.edges:
            if edge.callee_id in affected_symbol_ids and edge.caller_id in symbol_map:
                callers.add(symbol_map[edge.caller_id])

        # 2. Dependents: symbols that reference affected symbols
        dependents: set[Symbol] = set()
        for edge in repo.reference_graph.edges:
            source_id, target_id, _rel_type = edge
            if target_id in affected_symbol_ids and source_id in symbol_map:
                dependents.add(symbol_map[source_id])

        # 3. Shared modules: modules containing both affected and unaffected symbols
        affected_files: set[str] = set()
        for sid in affected_symbol_ids:
            if sid in symbol_map:
                affected_files.add(symbol_map[sid].file)
        all_files: set[str] = {s.file for s in repo.symbols}
        shared_modules = tuple(sorted(affected_files & all_files))

        # 4. Cross-service references: detect service boundaries via file paths
        cross_service: list[tuple[str, str, str]] = []
        for edge in repo.reference_graph.edges:
            source_id, target_id, _rel_type = edge
            if source_id in symbol_map and target_id in symbol_map:
                src_sym = symbol_map[source_id]
                tgt_sym = symbol_map[target_id]
                src_service = self._infer_service(src_sym.file)
                tgt_service = self._infer_service(tgt_sym.file)
                if src_service != tgt_service and target_id in affected_symbol_ids:
                    cross_service.append((src_service, tgt_service, target_id))

        # 5. Fan-in: count callers per affected symbol
        fan_in: dict[str, int] = defaultdict(int)
        for edge in repo.call_graph.edges:
            if edge.callee_id in affected_symbol_ids:
                fan_in[edge.callee_id] += 1

        # 6. Fan-out: count callees per affected symbol
        fan_out: dict[str, int] = defaultdict(int)
        for edge in repo.call_graph.edges:
            if edge.caller_id in affected_symbol_ids:
                fan_out[edge.caller_id] += 1

        # 7. Dependency depth: BFS from entry points to changed symbols
        depth = self._compute_dependency_depth(repo, affected_symbol_ids)

        dependency_model = DependencyModel(
            callers=tuple(sorted(callers, key=lambda s: s.id)),
            dependents=tuple(sorted(dependents, key=lambda s: s.id)),
            shared_modules=shared_modules,
            cross_service_references=tuple(sorted(cross_service)),
            fan_in=dict(fan_in),
            fan_out=dict(fan_out),
            dependency_depth=depth,
        )

        # Enrich the composed model with the dependency model
        context.composed_model = model.__class__(
            repository=model.repository,
            change=model.change,
            behavior=model.behavior,
            dependency=dependency_model,
            data=model.data,
            event=model.event,
            validation=model.validation,
            api=model.api if hasattr(model, 'api') else None,
            metrics=model.metrics if hasattr(model, 'metrics') else None,
        )

        return context

    @staticmethod
    def _infer_service(file_path: str) -> str:
        """
        Infer a service name from a file path.

        Uses the top-level directory as the service boundary.
        E.g., 'checkout/service.py' -> 'checkout'
        """
        parts = file_path.split("/")
        if len(parts) >= 2:
            return parts[0]
        return "root"

    @staticmethod
    def _compute_dependency_depth(
        repo: "RepositoryModel",
        affected_symbol_ids: set[str],
    ) -> int:
        """
        Compute the maximum BFS depth from entry points to affected symbols.

        Uses the call graph to find the shortest path from any entry point
        to any affected symbol, then returns the maximum depth found.
        """
        if not affected_symbol_ids:
            return 0

        # Build adjacency: caller -> list of callees
        adj: dict[str, list[str]] = defaultdict(list)
        for edge in repo.call_graph.edges:
            adj[edge.caller_id].append(edge.callee_id)

        # BFS from each entry point
        entry_point_ids = {ep.handler_id for ep in repo.entry_points}
        max_depth = 0
        visited: set[str] = set()

        for entry_id in entry_point_ids:
            queue: deque[tuple[str, int]] = deque()
            queue.append((entry_id, 0))
            visited.add(entry_id)

            while queue:
                current, current_depth = queue.popleft()

                if current in affected_symbol_ids:
                    max_depth = max(max_depth, current_depth)

                for neighbor in adj.get(current, []):
                    if neighbor not in visited:
                        visited.add(neighbor)
                        queue.append((neighbor, current_depth + 1))

        return max_depth
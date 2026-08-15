"""Base classes for operational compiler passes."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from engine.behavior.model import BehaviorModel
from engine.change.model import ChangeModel, RepositoryDelta
from engine.operational.model import OperationalChangeModel
from engine.repository.model import RepositoryModel, Symbol


@dataclass
class OperationalPassContext:
    """
    Context passed between operational compiler passes.

    This is a mutable container that accumulates state as passes execute.
    """

    # Input models (set before first pass)
    repository_model: RepositoryModel | None = None
    repository_delta: RepositoryDelta | None = None
    change_model: ChangeModel | None = None
    behavior_model: BehaviorModel | None = None

    # Composition outputs
    composed_model: OperationalChangeModel | None = None
    consistency_errors: list[str] = field(default_factory=list)

    # Enrichment analysis outputs (cached for pass chaining)
    dependency_model: object | None = None
    data_model: object | None = None
    event_model: object | None = None
    api_model: object | None = None
    validation_model: object | None = None

    # Metadata
    metadata: dict[str, Any] = field(default_factory=dict)

    # Caches for compiler passes
    _affected_symbol_ids: set[str] | None = field(default=None, init=False, repr=False)
    _symbol_map: dict[str, Symbol] | None = field(default=None, init=False, repr=False)
    _callees_of: dict[str, list[str]] | None = field(
        default=None, init=False, repr=False
    )
    _callers_of: dict[str, list[str]] | None = field(
        default=None, init=False, repr=False
    )
    _reachable_ids: set[str] | None = field(default=None, init=False, repr=False)

    @property
    def has_consistency_errors(self) -> bool:
        """Check if any consistency errors were found."""
        return len(self.consistency_errors) > 0

    @property
    def discovery_metrics(self) -> Any | None:
        """Get discovery metrics from metadata if present."""
        return self.metadata.get("discovery_metrics")

    def get_affected_symbol_ids(self) -> set[str]:
        """Lazy-load and cache affected symbol IDs.

        Extracts affected symbol IDs from:
        - ImpactSurface.affected_symbols (new architecture — BehaviorCompiler output)
        - BehaviorModel.behaviors (legacy)
        - ChangeFacts / ChangeModel changed symbols
        """
        if self._affected_symbol_ids is not None:
            return self._affected_symbol_ids

        affected: set[str] = set()

        # Check behavior model / ImpactSurface
        behavior = self.behavior_model or (
            self.composed_model.behavior if self.composed_model else None
        )
        if behavior is not None:
            if hasattr(behavior, "behaviors"):
                # Legacy BehaviorModel path
                for b in behavior.behaviors:
                    affected.add(b.root_symbol_id)
                    affected.update(b.changed_symbol_ids)
            elif hasattr(behavior, "affected_symbols"):
                # New ImpactSurface path — includes all traversal-discovered symbols
                for sym_id in behavior.affected_symbols:
                    affected.add(str(sym_id))

        # Check change model / ChangeFacts
        change = self.change_model or (
            self.composed_model.change if self.composed_model else None
        )
        if change is not None:
            if hasattr(change, "changed_symbols"):
                for cs in change.changed_symbols:
                    affected.add(str(cs.symbol_id))
            if hasattr(change, "added_symbols"):
                for s in change.added_symbols:
                    affected.add(str(getattr(s, "id", getattr(s, "symbol_id", str(s)))))
            if hasattr(change, "removed_symbols"):
                for s in change.removed_symbols:
                    affected.add(str(getattr(s, "id", getattr(s, "symbol_id", str(s)))))
            if hasattr(change, "modified_symbols"):
                for ms in change.modified_symbols:
                    sym = getattr(ms, "symbol", ms)
                    affected.add(
                        str(getattr(sym, "id", getattr(sym, "symbol_id", str(sym))))
                    )

        self._affected_symbol_ids = affected
        return affected

    def get_symbol_map(self) -> dict[str, Symbol]:
        """Lazy-load and cache repository symbol map."""
        if self._symbol_map is not None:
            return self._symbol_map

        repo = self.repository_model or (
            self.composed_model.repository if self.composed_model else None
        )
        if repo is None:
            return {}

        if hasattr(repo, "symbols"):
            symbol_map = {s.id: s for s in repo.symbols}
        elif hasattr(repo, "get_symbol"):
            symbol_map = {}
            for sym_id in self.get_affected_symbol_ids():
                s = repo.get_symbol(sym_id)
                if s is not None:
                    symbol_map[sym_id] = s
        else:
            symbol_map = {}

        self._symbol_map = symbol_map
        return symbol_map

    def _build_adjacency(self) -> None:
        """Helper to build adjacency maps once."""
        if self._callees_of is not None and self._callers_of is not None:
            return

        repo = self.repository_model or (
            self.composed_model.repository if self.composed_model else None
        )
        from collections import defaultdict

        callees: dict[str, list[str]] = defaultdict(list)
        callers: dict[str, list[str]] = defaultdict(list)
        if (
            repo is not None
            and hasattr(repo, "call_graph")
            and repo.call_graph is not None
        ):
            for edge in repo.call_graph.edges:
                callees[edge.caller_id].append(edge.callee_id)
                callers[edge.callee_id].append(edge.caller_id)
        elif (
            repo is not None
            and hasattr(repo, "get_callees")
            and hasattr(repo, "get_callers")
        ):
            for sym_id in self.get_affected_symbol_ids():
                for call in repo.get_callees(sym_id):
                    callees[sym_id].append(call.callee_id)
                for call in repo.get_callers(sym_id):
                    callers[sym_id].append(call.caller_id)
        self._callees_of = dict(callees)
        self._callers_of = dict(callers)

    def get_callees_of(self) -> dict[str, list[str]]:
        """Lazy-load and cache callee adjacency map."""
        self._build_adjacency()
        return self._callees_of or {}

    def get_callers_of(self) -> dict[str, list[str]]:
        """Lazy-load and cache caller adjacency map."""
        self._build_adjacency()
        return self._callers_of or {}

    def get_reachable_ids(self) -> set[str]:
        """Lazy-load and cache reachable symbol IDs via BFS."""
        if self._reachable_ids is not None:
            return self._reachable_ids

        seed_ids = self.get_affected_symbol_ids()
        callees = self.get_callees_of()

        from collections import deque

        reachable: set[str] = set()
        queue: deque[str] = deque(seed_ids)

        while queue:
            current = queue.popleft()
            if current in reachable:
                continue
            reachable.add(current)
            for neighbor in callees.get(current, []):
                if neighbor not in reachable:
                    queue.append(neighbor)

        self._reachable_ids = reachable - seed_ids
        return self._reachable_ids


class OperationalCompilerPass(ABC):
    """
    Base class for all operational compiler passes.

    Each pass has a single responsibility and transforms the context
    for the next pass in the pipeline.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the name of this pass."""

    @abstractmethod
    def run(self, context: OperationalPassContext) -> OperationalPassContext:
        """
        Execute the pass and return updated context.

        Args:
            context: The current pass context

        Returns:
            Updated pass context
        """

    def validate_input(self, context: OperationalPassContext) -> bool:
        """
        Validate that the context has required inputs for this pass.

        Override in subclasses to add validation logic.
        """
        return True

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name})"

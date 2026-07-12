"""Repository model - the output of Phase 1 compilation."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .symbol import Symbol
from .graphs import CallGraph, ReferenceGraph


class EntryPointKind(str, Enum):
    """Type of entry point."""
    REST_ENDPOINT = "rest_endpoint"
    GRAPHQL_RESOLVER = "graphql_resolver"
    RPC_HANDLER = "rpc_handler"
    CLI_COMMAND = "cli_command"
    SCHEDULED_JOB = "scheduled_job"
    WORKER_ENTRY = "worker_entry"
    EVENT_CONSUMER = "event_consumer"


@dataclass(frozen=True)
class EntryPoint:
    """
    Represents a discovered entry point in the repository.

    Entry points are framework-recognized handlers that serve as the
    root of executable behaviors.

    Attributes:
        kind: Type of entry point
        route: Route or trigger identifier (e.g., "POST /checkout")
        handler_id: Symbol id of the handler function/method
        metadata: Additional framework-specific metadata
    """
    kind: EntryPointKind
    route: str
    handler_id: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Validate entry point after initialization."""
        if not self.kind:
            raise ValueError("Entry point kind cannot be empty")
        if not self.route:
            raise ValueError("Entry point route cannot be empty")
        if not self.handler_id:
            raise ValueError("Entry point handler id cannot be empty")
        if isinstance(self.metadata, dict):
            object.__setattr__(self, 'metadata', dict(self.metadata))
        
        # Convert string kind to EntryPointKind if needed
        if isinstance(self.kind, str):
            object.__setattr__(self, 'kind', EntryPointKind(self.kind))


@dataclass(frozen=True)
class RepositoryModel:
    """
    The complete repository model produced by Phase 1 compilation.

    This is a deterministic, language-independent representation of a repository
    that answers: "What does this repository contain?"

    The RepositoryModel is the canonical representation consumed by all
    downstream compilers (Change, Behavior, Operational).

    Attributes:
        symbols: All discovered symbols in the repository
        call_graph: Repository-wide call graph
        reference_graph: Repository-wide reference graph
        entry_points: Discovered entry points
        metadata: Additional repository-level metadata
    """
    symbols: frozenset[Symbol]
    call_graph: CallGraph
    reference_graph: ReferenceGraph
    entry_points: tuple[EntryPoint, ...] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Validate repository model after initialization."""
        if not isinstance(self.symbols, frozenset):
            object.__setattr__(self, 'symbols', frozenset(self.symbols))
        if not isinstance(self.entry_points, tuple):
            object.__setattr__(self, 'entry_points', tuple(self.entry_points))
        if isinstance(self.metadata, dict):
            object.__setattr__(self, 'metadata', dict(self.metadata))

    def get_symbol_by_id(self, symbol_id: str) -> Symbol | None:
        """Get a symbol by its identifier."""
        for symbol in self.symbols:
            if symbol.id == symbol_id:
                return symbol
        return None

    def get_symbols_by_kind(self, kind: str) -> tuple[Symbol, ...]:
        """Get all symbols of a specific kind."""
        return tuple(s for s in self.symbols if s.kind == kind)

    def get_symbols_by_file(self, file: str) -> tuple[Symbol, ...]:
        """Get all symbols from a specific file."""
        return tuple(s for s in self.symbols if s.file == file)

    def get_calls_for(self, symbol_id: str) -> tuple:
        """Get all call edges where this symbol is the caller."""
        return self.call_graph.get_calls_for(symbol_id)

    def get_called_by(self, symbol_id: str) -> tuple:
        """Get all call edges where this symbol is the callee."""
        return self.call_graph.get_called_by(symbol_id)

    def get_entry_points_for_symbol(self, symbol_id: str) -> tuple[EntryPoint, ...]:
        """Get all entry points that reference this symbol."""
        return tuple(ep for ep in self.entry_points if ep.handler_id == symbol_id)

    def get_references_for(self, symbol_id: str) -> tuple:
        """Get all reference edges where this symbol is the source."""
        return self.reference_graph.get_references_for(symbol_id)

    def get_referenced_by(self, symbol_id: str) -> tuple:
        """Get all reference edges where this symbol is the target."""
        return self.reference_graph.get_referenced_by(symbol_id)
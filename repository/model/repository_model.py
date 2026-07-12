"""Repository model - the output of Phase 1 compilation."""

from dataclasses import dataclass, field
from typing import FrozenSet

from .graphs import CallEdge, CallGraph, EntryPoint, ReferenceGraph
from .symbol import Symbol


@dataclass(frozen=True)
class RepositoryModel:
    """
    The complete repository model produced by Phase 1 compilation.
    
    This is a deterministic, language-agnostic representation of a repository
    that answers: "What does this repository contain?"
    
    Attributes:
        symbols: Complete symbol inventory
        call_graph: Repository-wide directed call graph
        reference_graph: Symbol-to-symbol references (imports, inheritance, etc.)
        entry_points: Externally reachable entry points
    """
    symbols: FrozenSet[Symbol]
    call_graph: CallGraph
    reference_graph: ReferenceGraph
    entry_points: tuple[EntryPoint, ...] = field(default_factory=tuple)
    
    def __post_init__(self):
        """Validate repository model after initialization."""
        # Convert entry_points to tuple if needed
        if isinstance(self.entry_points, list):
            object.__setattr__(self, 'entry_points', tuple(self.entry_points))
        
        # Ensure symbols is a FrozenSet
        if not isinstance(self.symbols, frozenset):
            object.__setattr__(self, 'symbols', frozenset(self.symbols))
    
    def get_symbol_by_id(self, symbol_id: str) -> Symbol | None:
        """Get a symbol by its stable identifier."""
        for symbol in self.symbols:
            if symbol.id == symbol_id:
                return symbol
        return None
    
    def get_symbols_by_kind(self, kind: str) -> FrozenSet[Symbol]:
        """Get all symbols of a specific kind."""
        return frozenset(s for s in self.symbols if s.kind == kind)
    
    def get_symbols_by_file(self, file_path: str) -> FrozenSet[Symbol]:
        """Get all symbols defined in a specific file."""
        return frozenset(s for s in self.symbols if s.file == file_path)
    
    def get_calls_for(self, symbol_id: str) -> tuple[CallEdge, ...]:
        """Get all call edges where this symbol is the caller."""
        return tuple(e for e in self.call_graph.edges if e.caller_id == symbol_id)
    
    def get_called_by(self, symbol_id: str) -> tuple[CallEdge, ...]:
        """Get all call edges where this symbol is the callee."""
        return tuple(e for e in self.call_graph.edges if e.callee_id == symbol_id)
    
    def get_references_to(self, symbol_id: str) -> tuple[tuple[str, str, str], ...]:
        """Get all references to a specific symbol."""
        return tuple(e for e in self.reference_graph.edges if e[1] == symbol_id)
    
    def get_references_from(self, symbol_id: str) -> tuple[tuple[str, str, str], ...]:
        """Get all references from a specific symbol."""
        return tuple(e for e in self.reference_graph.edges if e[0] == symbol_id)
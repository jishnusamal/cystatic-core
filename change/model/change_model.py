"""Change model - identifies what changed from a code diff."""

from dataclasses import dataclass, field
from typing import FrozenSet

from language_adapters.model import Symbol
from .changes import (
    FunctionBodyChange,
    SignatureChange,
    VisibilityChange,
    DecoratorChange,
    SuperclassChange,
    InterfaceChange,
    EndpointAnnotationChange,
)


@dataclass(frozen=True)
class ImportChange:
    """Represents a change to an import statement."""
    file: str
    old_import: str | None
    new_import: str | None
    change_type: str  # "added", "removed", "modified"


@dataclass(frozen=True)
class EndpointChange:
    """Represents a change to an API endpoint."""
    symbol_id: str
    old_endpoint: str | None
    new_endpoint: str | None
    old_method: str | None
    new_method: str | None
    change_type: str  # "added", "removed", "modified"


@dataclass(frozen=True)
class ModifiedSymbol:
    """
    Represents a symbol that was modified.
    
    Contains the symbol and all structural changes detected.
    """
    symbol: Symbol
    changes: tuple[
        FunctionBodyChange |
        SignatureChange |
        VisibilityChange |
        DecoratorChange |
        SuperclassChange |
        InterfaceChange |
        EndpointAnnotationChange,
        ...
    ] = field(default_factory=tuple)
    
    def __post_init__(self):
        """Ensure changes is a tuple."""
        if not isinstance(self.changes, tuple):
            object.__setattr__(self, 'changes', tuple(self.changes))


@dataclass(frozen=True)
class ChangeModel:
    """
    The complete change model produced by change compilation.
    
    This is a deterministic, language-agnostic representation of a pull request
    that answers: "What exactly changed?"
    
    Attributes:
        added_symbols: Symbols that were added in this change
        removed_symbols: Symbols that were removed in this change
        modified_symbols: Symbols that were modified, with change details
        changed_imports: Import statements that changed
        changed_endpoints: API endpoints that changed
    """
    added_symbols: tuple[Symbol, ...]
    removed_symbols: tuple[Symbol, ...]
    modified_symbols: tuple[ModifiedSymbol, ...]
    changed_imports: tuple[ImportChange, ...]
    changed_endpoints: tuple[EndpointChange, ...]
    
    def __post_init__(self):
        """Validate change model after initialization."""
        # Ensure added_symbols is a tuple
        if not isinstance(self.added_symbols, tuple):
            object.__setattr__(self, 'added_symbols', tuple(self.added_symbols))
        
        # Ensure removed_symbols is a tuple
        if not isinstance(self.removed_symbols, tuple):
            object.__setattr__(self, 'removed_symbols', tuple(self.removed_symbols))
        
        # Ensure modified_symbols is a tuple
        if not isinstance(self.modified_symbols, tuple):
            object.__setattr__(self, 'modified_symbols', tuple(self.modified_symbols))
        
        # Ensure changed_imports is a tuple
        if not isinstance(self.changed_imports, tuple):
            object.__setattr__(self, 'changed_imports', tuple(self.changed_imports))
        
        # Ensure changed_endpoints is a tuple
        if not isinstance(self.changed_endpoints, tuple):
            object.__setattr__(self, 'changed_endpoints', tuple(self.changed_endpoints))
    
    def get_added_symbols_by_kind(self, kind: str) -> tuple[Symbol, ...]:
        """Get all added symbols of a specific kind."""
        return tuple(s for s in self.added_symbols if s.kind == kind)
    
    def get_removed_symbols_by_kind(self, kind: str) -> tuple[Symbol, ...]:
        """Get all removed symbols of a specific kind."""
        return tuple(s for s in self.removed_symbols if s.kind == kind)
    
    def get_modified_symbols_by_kind(self, kind: str) -> tuple[ModifiedSymbol, ...]:
        """Get all modified symbols of a specific kind."""
        return tuple(ms for ms in self.modified_symbols if ms.symbol.kind == kind)
    
    def get_changes_for_symbol(self, symbol_id: str) -> ModifiedSymbol | None:
        """Get modification details for a specific symbol."""
        for modified in self.modified_symbols:
            if modified.symbol.id == symbol_id:
                return modified
        return None
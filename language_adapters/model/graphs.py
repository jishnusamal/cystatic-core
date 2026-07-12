"""Graph models for the repository."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CallEdge:
    """
    Represents a directed call relationship between two symbols.

    Attributes:
        caller_id: Symbol id of the caller
        callee_id: Symbol id of the callee
        call_type: Type of call (direct, indirect, dynamic)
        file: Source file where the call occurs
        line: Line number where the call occurs
    """
    caller_id: str
    callee_id: str
    call_type: str = "direct"
    file: str = ""
    line: int = 0

    def __post_init__(self):
        """Validate call edge after initialization."""
        if not self.caller_id:
            raise ValueError("Caller id cannot be empty")
        if not self.callee_id:
            raise ValueError("Callee id cannot be empty")


@dataclass(frozen=True)
class CallGraph:
    """
    Repository-wide call graph.

    Contains all direct call relationships between symbols in the repository.
    """
    edges: tuple[CallEdge, ...] = field(default_factory=tuple)

    def __post_init__(self):
        """Ensure edges is a tuple."""
        if isinstance(self.edges, list):
            object.__setattr__(self, 'edges', tuple(self.edges))

    def get_calls_for(self, symbol_id: str) -> tuple[CallEdge, ...]:
        """Get all call edges where this symbol is the caller."""
        return tuple(e for e in self.edges if e.caller_id == symbol_id)

    def get_called_by(self, symbol_id: str) -> tuple[CallEdge, ...]:
        """Get all call edges where this symbol is the callee."""
        return tuple(e for e in self.edges if e.callee_id == symbol_id)


@dataclass(frozen=True)
class ReferenceEdge:
    """
    Represents a reference relationship between two symbols.

    Attributes:
        source_id: Symbol id of the source (referencer)
        target_id: Symbol id of the target (referenced)
        relation_type: Type of relationship (import, inheritance, etc.)
    """
    source_id: str
    target_id: str
    relation_type: str = "reference"

    def __post_init__(self):
        """Validate reference edge after initialization."""
        if not self.source_id:
            raise ValueError("Source id cannot be empty")
        if not self.target_id:
            raise ValueError("Target id cannot be empty")


@dataclass(frozen=True)
class ReferenceGraph:
    """
    Repository-wide reference graph.

    Contains all reference relationships between symbols (imports, inheritance, etc.).
    """
    edges: tuple[ReferenceEdge, ...] = field(default_factory=tuple)

    def __post_init__(self):
        """Ensure edges is a tuple."""
        if isinstance(self.edges, list):
            object.__setattr__(self, 'edges', tuple(self.edges))

    def get_references_for(self, symbol_id: str) -> tuple[ReferenceEdge, ...]:
        """Get all reference edges where this symbol is the source."""
        return tuple(e for e in self.edges if e.source_id == symbol_id)

    def get_referenced_by(self, symbol_id: str) -> tuple[ReferenceEdge, ...]:
        """Get all reference edges where this symbol is the target."""
        return tuple(e for e in self.edges if e.target_id == symbol_id)


@dataclass(frozen=True)
class TypeRelationshipEdge:
    """
    Represents a type relationship between two symbols.

    Attributes:
        source_id: Symbol id of the source type
        target_id: Symbol id of the target type
        relation_type: Type of relationship (extends, implements, composes, uses_generic)
        metadata: Additional information about the relationship
    """
    source_id: str
    target_id: str
    relation_type: str = "extends"
    metadata: dict[str, str] = field(default_factory=dict)

    def __post_init__(self):
        """Validate type relationship edge after initialization."""
        if not self.source_id:
            raise ValueError("Source id cannot be empty")
        if not self.target_id:
            raise ValueError("Target id cannot be empty")
        if isinstance(self.metadata, dict):
            object.__setattr__(self, 'metadata', dict(self.metadata))


@dataclass(frozen=True)
class TypeRelationshipGraph:
    """
    Repository-wide type relationship graph.

    Contains inheritance, interface implementation, composition,
    and generic type reference relationships.
    """
    edges: tuple[TypeRelationshipEdge, ...] = field(default_factory=tuple)

    def __post_init__(self):
        """Ensure edges is a tuple."""
        if isinstance(self.edges, list):
            object.__setattr__(self, 'edges', tuple(self.edges))

    def get_relationships_for(self, symbol_id: str) -> tuple[TypeRelationshipEdge, ...]:
        """Get all type relationships where this symbol is the source."""
        return tuple(e for e in self.edges if e.source_id == symbol_id)

    def get_relationships_to(self, symbol_id: str) -> tuple[TypeRelationshipEdge, ...]:
        """Get all type relationships where this symbol is the target."""
        return tuple(e for e in self.edges if e.target_id == symbol_id)

    def get_inheritance_chain(self, symbol_id: str) -> tuple[TypeRelationshipEdge, ...]:
        """Get all inheritance relationships for a symbol."""
        return tuple(
            e for e in self.edges
            if (e.source_id == symbol_id or e.target_id == symbol_id)
            and e.relation_type in ('extends', 'implements')
        )
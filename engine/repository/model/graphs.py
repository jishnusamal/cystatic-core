"""Graph models for the repository."""

import sys
from dataclasses import dataclass, field
from typing import Any

from .evidence import Evidence, FileLocation


@dataclass(slots=True, frozen=True)
class CallEdge:
    """
    Represents a directed call relationship between two symbols.

    Attributes:
        caller_id: Symbol id of the caller
        callee_id: Symbol id of the callee
        call_type: Type of call (direct, indirect, dynamic)
        file: Source file where the call occurs
        line: Line number where the call occurs
        evidence: Provenance evidence for this call edge
    """

    caller_id: str
    callee_id: str
    call_type: str = "direct"
    file: str = ""
    line: int = 0
    evidence: Evidence | None = None

    def __post_init__(self):
        """Validate call edge after initialization."""
        if not self.caller_id:
            raise ValueError("Caller id cannot be empty")
        if not self.callee_id:
            raise ValueError("Callee id cannot be empty")
        object.__setattr__(self, "caller_id", sys.intern(self.caller_id))
        object.__setattr__(self, "callee_id", sys.intern(self.callee_id))
        object.__setattr__(self, "call_type", sys.intern(self.call_type))
        if self.file:
            object.__setattr__(self, "file", sys.intern(self.file))
        if self.evidence is None and self.file:
            object.__setattr__(
                self,
                "evidence",
                Evidence(
                    file_location=FileLocation(
                        file=self.file,
                        start_line=max(self.line, 1),
                        end_line=max(self.line, 1),
                    ),
                ),
            )


@dataclass(frozen=True)
class CallGraph:
    """
    Repository-wide call graph.

    Contains all direct call relationships between symbols in the repository.
    """

    edges: tuple[CallEdge, ...] = field(default_factory=tuple)
    _indexes: dict[str, Any] = field(
        default_factory=dict, init=False, repr=False, compare=False
    )

    def __post_init__(self):
        """Ensure edges is a tuple and initialize index container."""
        if isinstance(self.edges, list):
            object.__setattr__(self, "edges", tuple(self.edges))
        object.__setattr__(self, "_indexes", {})

    def _build_outgoing(self) -> dict[str, tuple[CallEdge, ...]]:
        outgoing: dict[str, list[CallEdge]] = {}
        for edge in self.edges:
            outgoing.setdefault(edge.caller_id, []).append(edge)
        return {k: tuple(v) for k, v in outgoing.items()}

    def _build_incoming(self) -> dict[str, tuple[CallEdge, ...]]:
        incoming: dict[str, list[CallEdge]] = {}
        for edge in self.edges:
            incoming.setdefault(edge.callee_id, []).append(edge)
        return {k: tuple(v) for k, v in incoming.items()}

    @property
    def outgoing(self) -> dict[str, tuple[CallEdge, ...]]:
        if "outgoing" not in self._indexes:
            self._indexes["outgoing"] = self._build_outgoing()
        return self._indexes["outgoing"]

    @property
    def incoming(self) -> dict[str, tuple[CallEdge, ...]]:
        if "incoming" not in self._indexes:
            self._indexes["incoming"] = self._build_incoming()
        return self._indexes["incoming"]

    @property
    def _outgoing(self) -> dict[str, tuple[CallEdge, ...]]:
        return self.outgoing

    @property
    def _incoming(self) -> dict[str, tuple[CallEdge, ...]]:
        return self.incoming

    def get_calls_for(self, symbol_id: str) -> tuple[CallEdge, ...]:
        """Get all call edges where this symbol is the caller."""
        return self.outgoing.get(symbol_id, ())

    def get_called_by(self, symbol_id: str) -> tuple[CallEdge, ...]:
        """Get all call edges where this symbol is the callee."""
        return self.incoming.get(symbol_id, ())

    def __getstate__(self):
        state = self.__dict__.copy()
        state["_indexes"] = {}
        return state

    def __setstate__(self, state):
        for k, v in state.items():
            object.__setattr__(self, k, v)


@dataclass(slots=True, frozen=True)
class ReferenceEdge:
    """
    Represents a reference relationship between two symbols.

    Attributes:
        source_id: Symbol id of the source (referencer)
        target_id: Symbol id of the target (referenced)
        relation_type: Type of relationship (import, inheritance, etc.)
        evidence: Provenance evidence for this reference edge
    """

    source_id: str
    target_id: str
    relation_type: str = "reference"
    evidence: Evidence | None = None

    def __post_init__(self):
        """Validate reference edge after initialization."""
        if not self.source_id:
            raise ValueError("Source id cannot be empty")
        if not self.target_id:
            raise ValueError("Target id cannot be empty")
        object.__setattr__(self, "source_id", sys.intern(self.source_id))
        object.__setattr__(self, "target_id", sys.intern(self.target_id))
        object.__setattr__(self, "relation_type", sys.intern(self.relation_type))


@dataclass(frozen=True)
class ReferenceGraph:
    """
    Repository-wide reference graph.

    Contains all reference relationships between symbols (imports, inheritance, etc.).
    """

    edges: tuple[ReferenceEdge, ...] = field(default_factory=tuple)
    _indexes: dict[str, Any] = field(
        default_factory=dict, init=False, repr=False, compare=False
    )

    def __post_init__(self):
        """Ensure edges is a tuple and initialize index container."""
        if isinstance(self.edges, list):
            object.__setattr__(self, "edges", tuple(self.edges))
        object.__setattr__(self, "_indexes", {})

    def _build_outgoing(self) -> dict[str, tuple[ReferenceEdge, ...]]:
        outgoing: dict[str, list[ReferenceEdge]] = {}
        for edge in self.edges:
            outgoing.setdefault(edge.source_id, []).append(edge)
        return {k: tuple(v) for k, v in outgoing.items()}

    def _build_incoming(self) -> dict[str, tuple[ReferenceEdge, ...]]:
        incoming: dict[str, list[ReferenceEdge]] = {}
        for edge in self.edges:
            incoming.setdefault(edge.target_id, []).append(edge)
        return {k: tuple(v) for k, v in incoming.items()}

    @property
    def outgoing(self) -> dict[str, tuple[ReferenceEdge, ...]]:
        if "outgoing" not in self._indexes:
            self._indexes["outgoing"] = self._build_outgoing()
        return self._indexes["outgoing"]

    @property
    def incoming(self) -> dict[str, tuple[ReferenceEdge, ...]]:
        if "incoming" not in self._indexes:
            self._indexes["incoming"] = self._build_incoming()
        return self._indexes["incoming"]

    @property
    def _outgoing(self) -> dict[str, tuple[ReferenceEdge, ...]]:
        return self.outgoing

    @property
    def _incoming(self) -> dict[str, tuple[ReferenceEdge, ...]]:
        return self.incoming

    def get_references_for(self, symbol_id: str) -> tuple[ReferenceEdge, ...]:
        """Get all reference edges where this symbol is the source."""
        return self.outgoing.get(symbol_id, ())

    def get_referenced_by(self, symbol_id: str) -> tuple[ReferenceEdge, ...]:
        """Get all reference edges where this symbol is the target."""
        return self.incoming.get(symbol_id, ())

    def __getstate__(self):
        state = self.__dict__.copy()
        state["_indexes"] = {}
        return state

    def __setstate__(self, state):
        for k, v in state.items():
            object.__setattr__(self, k, v)


@dataclass(frozen=True)
class TypeRelationshipEdge:
    """
    Represents a type relationship between two symbols.

    Attributes:
        source_id: Symbol id of the source type
        target_id: Symbol id of the target type
        relation_type: Type of relationship (extends, implements, composes, uses_generic)
        metadata: Additional information about the relationship
        evidence: Provenance evidence for this type relationship
    """

    source_id: str
    target_id: str
    relation_type: str = "extends"
    metadata: dict[str, str] = field(default_factory=dict)
    evidence: Evidence | None = None

    def __post_init__(self):
        """Validate type relationship edge after initialization."""
        if not self.source_id:
            raise ValueError("Source id cannot be empty")
        if not self.target_id:
            raise ValueError("Target id cannot be empty")
        if isinstance(self.metadata, dict):
            object.__setattr__(self, "metadata", dict(self.metadata))


@dataclass(frozen=True)
class TypeRelationshipGraph:
    """
    Repository-wide type relationship graph.

    Contains inheritance, interface implementation, composition,
    and generic type reference relationships.
    """

    edges: tuple[TypeRelationshipEdge, ...] = field(default_factory=tuple)
    _indexes: dict[str, Any] = field(
        default_factory=dict, init=False, repr=False, compare=False
    )

    def __post_init__(self):
        """Ensure edges is a tuple and initialize index container."""
        if isinstance(self.edges, list):
            object.__setattr__(self, "edges", tuple(self.edges))
        object.__setattr__(self, "_indexes", {})

    def _build_outgoing(self) -> dict[str, tuple[TypeRelationshipEdge, ...]]:
        outgoing: dict[str, list[TypeRelationshipEdge]] = {}
        for edge in self.edges:
            outgoing.setdefault(edge.source_id, []).append(edge)
        return {k: tuple(v) for k, v in outgoing.items()}

    def _build_incoming(self) -> dict[str, tuple[TypeRelationshipEdge, ...]]:
        incoming: dict[str, list[TypeRelationshipEdge]] = {}
        for edge in self.edges:
            incoming.setdefault(edge.target_id, []).append(edge)
        return {k: tuple(v) for k, v in incoming.items()}

    @property
    def outgoing(self) -> dict[str, tuple[TypeRelationshipEdge, ...]]:
        if "outgoing" not in self._indexes:
            self._indexes["outgoing"] = self._build_outgoing()
        return self._indexes["outgoing"]

    @property
    def incoming(self) -> dict[str, tuple[TypeRelationshipEdge, ...]]:
        if "incoming" not in self._indexes:
            self._indexes["incoming"] = self._build_incoming()
        return self._indexes["incoming"]

    @property
    def _outgoing(self) -> dict[str, tuple[TypeRelationshipEdge, ...]]:
        return self.outgoing

    @property
    def _incoming(self) -> dict[str, tuple[TypeRelationshipEdge, ...]]:
        return self.incoming

    def get_relationships_for(self, symbol_id: str) -> tuple[TypeRelationshipEdge, ...]:
        """Get all type relationships where this symbol is the source."""
        return self.outgoing.get(symbol_id, ())

    def get_relationships_to(self, symbol_id: str) -> tuple[TypeRelationshipEdge, ...]:
        """Get all type relationships where this symbol is the target."""
        return self.incoming.get(symbol_id, ())

    def get_inheritance_chain(self, symbol_id: str) -> tuple[TypeRelationshipEdge, ...]:
        """Get all inheritance relationships for a symbol."""
        rels_from = self.get_relationships_for(symbol_id)
        rels_to = self.get_relationships_to(symbol_id)
        return tuple(
            e
            for e in (rels_from + rels_to)
            if e.relation_type in ("extends", "implements")
        )

    def __getstate__(self):
        state = self.__dict__.copy()
        state["_indexes"] = {}
        return state

    def __setstate__(self, state):
        for k, v in state.items():
            object.__setattr__(self, k, v)

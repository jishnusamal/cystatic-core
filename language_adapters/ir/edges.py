"""Language-agnostic edge types for the semantic graph."""

from __future__ import annotations

from enum import Enum, auto
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from language_adapters.ir.nodes import BaseNode


class EdgeType(Enum):
    CALLS = auto()
    CALLED_BY = auto()
    READS = auto()
    WRITES = auto()
    CREATES = auto()
    UPDATES = auto()
    DELETES = auto()
    USES = auto()
    VALIDATES = auto()
    NORMALIZES = auto()
    TESTS = auto()
    MIGRATES = auto()
    EXPOSES = auto()
    PUBLISHES = auto()
    SUBSCRIBES = auto()
    SENDS_HTTP = auto()
    EMITS_EVENT = auto()
    HAS_FIELD = auto()
    HAS_PARAMETER = auto()
    RETURNS = auto()
    RAISES = auto()
    INHERITS = auto()
    DECORATED_BY = auto()


@dataclass
class BaseEdge:
    """Base class for all semantic graph edges."""

    edge_type: Optional[EdgeType] = None
    source: Optional[BaseNode] = None
    target: Optional[BaseNode] = None
    properties: Dict[str, Any] = field(default_factory=dict)
    change_type: str = "modified"  # added, removed, modified

    def __hash__(self) -> int:
        return hash((self.edge_type, self.source, self.target))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, BaseEdge):
            return NotImplemented
        return (
            self.edge_type == other.edge_type
            and self.source == other.source
            and self.target == other.target
        )

    def __lt__(self, other: BaseEdge) -> bool:
        """Support sorting for deduplication."""
        return (self.edge_type, self.source, self.target) < (other.edge_type, other.source, other.target)


@dataclass
class CallsEdge(BaseEdge):
    """Source function/method calls target function/method."""

    call_type: str = "direct"  # direct, indirect, super, classmethod, staticmethod
    line_number: Optional[int] = None
    _edge_type_override: EdgeType = EdgeType.CALLS

    def __post_init__(self) -> None:
        self.edge_type = self._edge_type_override
        object.__delattr__(self, '_edge_type_override')


@dataclass
class CalledByEdge(BaseEdge):
    """Source function/method is called by target function/method."""

    call_type: str = "direct"
    line_number: Optional[int] = None
    _edge_type_override: EdgeType = EdgeType.CALLED_BY

    def __post_init__(self) -> None:
        self.edge_type = self._edge_type_override
        object.__delattr__(self, '_edge_type_override')


@dataclass
class ReadsEdge(BaseEdge):
    """Source reads target (model, field, file, etc.)."""

    _edge_type_override: EdgeType = EdgeType.READS

    def __post_init__(self) -> None:
        self.edge_type = self._edge_type_override
        object.__delattr__(self, '_edge_type_override')


@dataclass
class WritesEdge(BaseEdge):
    """Source writes target."""

    _edge_type_override: EdgeType = EdgeType.WRITES

    def __post_init__(self) -> None:
        self.edge_type = self._edge_type_override
        object.__delattr__(self, '_edge_type_override')


@dataclass
class CreatesEdge(BaseEdge):
    """Source creates target instance."""

    _edge_type_override: EdgeType = EdgeType.CREATES

    def __post_init__(self) -> None:
        self.edge_type = self._edge_type_override
        object.__delattr__(self, '_edge_type_override')


@dataclass
class UpdatesEdge(BaseEdge):
    """Source updates target."""

    _edge_type_override: EdgeType = EdgeType.UPDATES

    def __post_init__(self) -> None:
        self.edge_type = self._edge_type_override
        object.__delattr__(self, '_edge_type_override')


@dataclass
class DeletesEdge(BaseEdge):
    """Source deletes target."""

    _edge_type_override: EdgeType = EdgeType.DELETES

    def __post_init__(self) -> None:
        self.edge_type = self._edge_type_override
        object.__delattr__(self, '_edge_type_override')


@dataclass
class UsesEdge(BaseEdge):
    """Source uses target (generic dependency)."""

    _edge_type_override: EdgeType = EdgeType.USES

    def __post_init__(self) -> None:
        self.edge_type = self._edge_type_override
        object.__delattr__(self, '_edge_type_override')


@dataclass
class ValidatesEdge(BaseEdge):
    """Source validates target field/value."""

    validation_type: str = ""  # raise, assert, if, schema, serializer, pydantic
    _edge_type_override: EdgeType = EdgeType.VALIDATES

    def __post_init__(self) -> None:
        self.edge_type = self._edge_type_override
        object.__delattr__(self, '_edge_type_override')


@dataclass
class NormalizesEdge(BaseEdge):
    """Source normalizes target field/value."""

    normalization_type: str = ""  # lower, upper, strip, slugify, hash, etc.
    _edge_type_override: EdgeType = EdgeType.NORMALIZES

    def __post_init__(self) -> None:
        self.edge_type = self._edge_type_override
        object.__delattr__(self, '_edge_type_override')


@dataclass
class TestsEdge(BaseEdge):
    """Source test tests target function."""

    _edge_type_override: EdgeType = EdgeType.TESTS

    def __post_init__(self) -> None:
        self.edge_type = self._edge_type_override
        object.__delattr__(self, '_edge_type_override')


@dataclass
class MigratesEdge(BaseEdge):
    """Source migration modifies target."""

    operation: str = ""  # create_table, add_column, drop_column, alter_column, etc.
    _edge_type_override: EdgeType = EdgeType.MIGRATES

    def __post_init__(self) -> None:
        self.edge_type = self._edge_type_override
        object.__delattr__(self, '_edge_type_override')


@dataclass
class ExposesEdge(BaseEdge):
    """Source endpoint exposes target function."""

    _edge_type_override: EdgeType = EdgeType.EXPOSES

    def __post_init__(self) -> None:
        self.edge_type = self._edge_type_override
        object.__delattr__(self, '_edge_type_override')


@dataclass
class PublishesEdge(BaseEdge):
    """Source publishes to target event/queue."""

    _edge_type_override: EdgeType = EdgeType.PUBLISHES

    def __post_init__(self) -> None:
        self.edge_type = self._edge_type_override
        object.__delattr__(self, '_edge_type_override')


@dataclass
class SubscribesEdge(BaseEdge):
    """Source subscribes to target event/queue."""

    _edge_type_override: EdgeType = EdgeType.SUBSCRIBES

    def __post_init__(self) -> None:
        self.edge_type = self._edge_type_override
        object.__delattr__(self, '_edge_type_override')


@dataclass
class SendsHttpEdge(BaseEdge):
    """Source sends HTTP request to target service."""

    method: str = "GET"
    url: Optional[str] = None
    _edge_type_override: EdgeType = EdgeType.SENDS_HTTP

    def __post_init__(self) -> None:
        self.edge_type = self._edge_type_override
        object.__delattr__(self, '_edge_type_override')


@dataclass
class EmitsEventEdge(BaseEdge):
    """Source emits target event."""

    _edge_type_override: EdgeType = EdgeType.EMITS_EVENT

    def __post_init__(self) -> None:
        self.edge_type = self._edge_type_override
        object.__delattr__(self, '_edge_type_override')


@dataclass
class HasFieldEdge(BaseEdge):
    """Source model has target field."""

    _edge_type_override: EdgeType = EdgeType.HAS_FIELD

    def __post_init__(self) -> None:
        self.edge_type = self._edge_type_override
        object.__delattr__(self, '_edge_type_override')


@dataclass
class HasParameterEdge(BaseEdge):
    """Source function has target parameter."""

    _edge_type_override: EdgeType = EdgeType.HAS_PARAMETER

    def __post_init__(self) -> None:
        self.edge_type = self._edge_type_override
        object.__delattr__(self, '_edge_type_override')


@dataclass
class ReturnsEdge(BaseEdge):
    """Source function returns target type."""

    _edge_type_override: EdgeType = EdgeType.RETURNS

    def __post_init__(self) -> None:
        self.edge_type = self._edge_type_override
        object.__delattr__(self, '_edge_type_override')


@dataclass
class RaisesEdge(BaseEdge):
    """Source function raises target exception."""

    _edge_type_override: EdgeType = EdgeType.RAISES

    def __post_init__(self) -> None:
        self.edge_type = self._edge_type_override
        object.__delattr__(self, '_edge_type_override')


@dataclass
class InheritsEdge(BaseEdge):
    """Source class inherits from target class."""

    _edge_type_override: EdgeType = EdgeType.INHERITS

    def __post_init__(self) -> None:
        self.edge_type = self._edge_type_override
        object.__delattr__(self, '_edge_type_override')


@dataclass
class DecoratedByEdge(BaseEdge):
    """Source function/method/class is decorated by target decorator."""

    _edge_type_override: EdgeType = EdgeType.DECORATED_BY

    def __post_init__(self) -> None:
        self.edge_type = self._edge_type_override
        object.__delattr__(self, '_edge_type_override')
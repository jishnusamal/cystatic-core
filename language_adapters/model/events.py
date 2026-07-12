"""Event models - event operations discovered in the repository."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .evidence import Evidence


class EventOperationKind(str, Enum):
    """Type of event operation."""
    PUBLISH = "publish"
    EMIT = "emit"
    DISPATCH = "dispatch"
    SEND = "send"
    BROADCAST = "broadcast"
    SUBSCRIBE = "subscribe"
    LISTEN = "listen"
    HANDLE = "handle"


@dataclass(frozen=True)
class EventConstruct:
    """
    Represents an event operation discovered in the repository.

    Examples: publish(), emit(), dispatch(), send() calls.

    Attributes:
        symbol_id: Symbol id of the calling function/method
        operation_kind: Type of event operation
        event_name: Name or type of the event
        framework: Framework identifying the event system
        file: Source file where the event operation occurs
        line: Line number where the event operation occurs
        evidence: Provenance evidence for this event construct
        metadata: Additional framework-specific metadata
    """
    symbol_id: str
    operation_kind: EventOperationKind
    event_name: str = ""
    framework: str = ""
    file: str = ""
    line: int = 0
    evidence: Evidence | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Validate event construct after initialization."""
        if not self.symbol_id:
            raise ValueError("Symbol id cannot be empty")
        if isinstance(self.operation_kind, str):
            object.__setattr__(self, 'operation_kind', EventOperationKind(self.operation_kind))
        if isinstance(self.metadata, dict):
            object.__setattr__(self, 'metadata', dict(self.metadata))
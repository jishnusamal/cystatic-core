from dataclasses import dataclass
from enum import Enum
from .ids import SymbolId, EventId


class EventPublicationType(str, Enum):
    """The style of event publication."""

    PUBLISH = "publish"
    EMIT = "emit"
    SEND = "send"
    PRODUCE = "produce"


class EventSubscriptionType(str, Enum):
    """The style of event subscription."""

    SUBSCRIBE = "subscribe"
    CONSUME = "consume"
    HANDLE = "handle"
    LISTEN = "listen"


@dataclass(frozen=True, slots=True)
class EventPublication:
    """Represents a code symbol publishing/emitting an event."""

    symbol_id: SymbolId
    event_id: EventId
    publication_type: EventPublicationType


@dataclass(frozen=True, slots=True)
class EventSubscription:
    """Represents a code symbol subscribing to/consuming an event."""

    symbol_id: SymbolId
    event_id: EventId
    subscription_type: EventSubscriptionType

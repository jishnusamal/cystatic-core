from dataclasses import dataclass
from enum import Enum
from .ids import SymbolId


class CallType(str, Enum):
    """The invocation dispatch mechanism."""

    DIRECT = "direct"
    METHOD = "method"
    CONSTRUCTOR = "constructor"
    ASYNC = "async"
    DYNAMIC = "dynamic"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class Call:
    """Represents a call dependency fact between two symbols."""

    caller_id: SymbolId
    callee_id: SymbolId
    call_type: CallType = CallType.DIRECT

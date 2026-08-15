from dataclasses import dataclass
from enum import Enum
from .ids import SymbolId, EndpointId

class EndpointMethod(str, Enum):
    """HTTP methods for endpoints."""
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"
    PATCH = "PATCH"
    OPTIONS = "OPTIONS"
    HEAD = "HEAD"
    ANY = "ANY"


@dataclass(frozen=True, slots=True)
class Endpoint:
    """Represents an HTTP endpoint fact exposed by a symbol."""
    id: EndpointId
    symbol_id: SymbolId
    method: EndpointMethod
    path: str
    framework: str

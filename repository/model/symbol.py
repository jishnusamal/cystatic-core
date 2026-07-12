"""Symbol model for repository compilation."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SymbolKind(str, Enum):
    """Type of symbol."""
    FUNCTION = "function"
    METHOD = "method"
    CLASS = "class"
    INTERFACE = "interface"
    MODULE = "module"
    CONSTANT = "constant"
    ENUM = "enum"
    VARIABLE = "variable"
    PROPERTY = "property"
    IMPORT = "import"


class SymbolVisibility(str, Enum):
    """Symbol visibility scope."""
    PUBLIC = "public"
    PRIVATE = "private"
    PROTECTED = "protected"
    INTERNAL = "internal"
    PACKAGE = "package"


def _make_hashable(obj: Any) -> Any:
    """Convert an object to a hashable form."""
    if isinstance(obj, dict):
        return tuple(sorted((k, _make_hashable(v)) for k, v in obj.items()))
    elif isinstance(obj, list):
        return tuple(_make_hashable(item) for item in obj)
    return obj


@dataclass(frozen=True)
class Symbol:
    """
    Represents a code symbol with stable identifier.
    
    Examples:
        python://checkout/service.py::confirm_checkout
        java://billing/InvoiceService#createInvoice
    """
    id: str
    name: str
    kind: SymbolKind
    language: str
    file: str
    range: tuple[int, int]  # (start_line, end_line)
    visibility: SymbolVisibility = SymbolVisibility.PUBLIC
    properties: dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Validate symbol after initialization."""
        if not self.id:
            raise ValueError("Symbol id cannot be empty")
        if not self.name:
            raise ValueError("Symbol name cannot be empty")
        if not self.language:
            raise ValueError("Symbol language cannot be empty")
        if not self.file:
            raise ValueError("Symbol file cannot be empty")
        if len(self.range) != 2 or self.range[0] > self.range[1]:
            raise ValueError(f"Invalid range: {self.range}")
    
    def __hash__(self) -> int:
        """Return hash of the symbol, making properties hashable."""
        # Convert properties to a hashable form
        hashable_properties = _make_hashable(self.properties)
        return hash((
            self.id,
            self.name,
            self.kind,
            self.language,
            self.file,
            self.range,
            self.visibility,
            hashable_properties
        ))

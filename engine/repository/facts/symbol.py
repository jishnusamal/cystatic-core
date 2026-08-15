from dataclasses import dataclass
from enum import Enum
from .ids import FileId, SymbolId

class SymbolKind(str, Enum):
    """Supported kinds of code symbols."""
    MODULE = "module"
    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"
    VARIABLE = "variable"
    CONSTANT = "constant"
    PROPERTY = "property"
    FIELD = "field"
    INTERFACE = "interface"
    ENUM = "enum"
    CONSTRUCTOR = "constructor"


class SymbolVisibility(str, Enum):
    """Access visibility modifiers."""
    PUBLIC = "public"
    PRIVATE = "private"
    PROTECTED = "protected"
    INTERNAL = "internal"
    PACKAGE = "package"


@dataclass(frozen=True, slots=True)
class Symbol:
    """Represents a code symbol fact."""
    id: SymbolId
    name: str
    file_id: FileId
    kind: SymbolKind
    language: str
    start_line: int
    end_line: int
    visibility: SymbolVisibility = SymbolVisibility.PUBLIC
    parent_symbol_id: SymbolId | None = None

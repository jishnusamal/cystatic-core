from dataclasses import dataclass
from enum import Enum
from .ids import SymbolId


class ReferenceType(str, Enum):
    """The type of generic reference."""

    REFERENCE = "reference"
    READ = "read"
    WRITE = "write"
    INSTANTIATE = "instantiate"
    TYPE_ANNOTATION = "type_annotation"


@dataclass(frozen=True, slots=True)
class Reference:
    """Represents a generic target-source reference fact."""

    source_id: SymbolId
    target_id: SymbolId
    relation_type: ReferenceType = ReferenceType.REFERENCE

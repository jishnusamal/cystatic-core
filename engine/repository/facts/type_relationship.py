from dataclasses import dataclass
from enum import Enum
from .ids import SymbolId


class TypeRelationshipType(str, Enum):
    """The kind of type relationship."""

    EXTENDS = "extends"
    IMPLEMENTS = "implements"
    INHERITS = "inherits"
    USES = "uses"
    RETURNS = "returns"
    PARAMETER = "parameter"
    FIELD_TYPE = "field_type"


@dataclass(frozen=True, slots=True)
class TypeRelationship:
    """Represents a type relationship fact between symbols."""

    source_id: SymbolId
    target_id: SymbolId
    relationship_type: TypeRelationshipType

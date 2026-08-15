from dataclasses import dataclass
from enum import Enum
from .ids import SymbolId, ResourceId

class DatabaseRelationshipType(str, Enum):
    """The type of operational access to the database resource."""
    READ = "read"
    WRITE = "write"
    INSERT = "insert"
    UPDATE = "update"
    DELETE = "delete"
    QUERY = "query"
    MIGRATE = "migrate"


@dataclass(frozen=True, slots=True)
class DatabaseRelationship:
    """Represents a database resource access fact by a symbol."""
    symbol_id: SymbolId
    resource_id: ResourceId
    relationship_type: DatabaseRelationshipType

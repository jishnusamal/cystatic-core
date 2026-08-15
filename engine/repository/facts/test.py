from dataclasses import dataclass
from enum import Enum
from .ids import SymbolId

class TestRelationshipType(str, Enum):
    """The type of testing relationship."""
    __test__ = False
    UNIT = "unit"
    INTEGRATION = "integration"
    E2E = "e2e"
    COVERS = "covers"
    ASSERTS = "asserts"


@dataclass(frozen=True, slots=True)
class TestRelationship:
    """Represents a relationship fact between a test symbol and the target code symbol."""
    __test__ = False
    test_symbol_id: SymbolId
    target_symbol_id: SymbolId
    relationship_type: TestRelationshipType

"""Model package - language-independent repository representation."""

from .symbol import Symbol, SymbolKind, SymbolVisibility
from .evidence import (
    Evidence,
    FileLocation,
    SymbolReference,
    CallReference,
    ImportReference,
    AnnotationReference,
)
from .graphs import (
    CallEdge,
    CallGraph,
    ReferenceEdge,
    ReferenceGraph,
    TypeRelationshipEdge,
    TypeRelationshipGraph,
)
from .repository_model import (
    RepositoryModel,
    EntryPoint,
    EntryPointKind,
    AsyncEntryPoint,
)
from .persistence import (
    PersistenceModel,
    PersistenceModelKind,
    RepositoryMethod,
    RepositoryMethodKind,
)
from .events import EventConstruct, EventOperationKind
from .tests import TestDefinition, TestFramework, TestFixture
from .configuration import ConfigurationReference, ConfigReferenceKind

__all__ = [
    # Symbol
    "Symbol",
    "SymbolKind",
    "SymbolVisibility",
    # Evidence
    "Evidence",
    "FileLocation",
    "SymbolReference",
    "CallReference",
    "ImportReference",
    "AnnotationReference",
    # Graphs
    "CallEdge",
    "CallGraph",
    "ReferenceEdge",
    "ReferenceGraph",
    "TypeRelationshipEdge",
    "TypeRelationshipGraph",
    # Repository Model
    "RepositoryModel",
    "EntryPoint",
    "EntryPointKind",
    "AsyncEntryPoint",
    # Persistence
    "PersistenceModel",
    "PersistenceModelKind",
    "RepositoryMethod",
    "RepositoryMethodKind",
    # Events
    "EventConstruct",
    "EventOperationKind",
    # Tests
    "TestDefinition",
    "TestFramework",
    "TestFixture",
    # Configuration
    "ConfigurationReference",
    "ConfigReferenceKind",
]
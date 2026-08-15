"""Model package - language-independent repository representation."""

from .configuration import ConfigReferenceKind, ConfigurationReference
from .events import EventConstruct, EventOperationKind
from .evidence import (
    AnnotationReference,
    CallReference,
    Evidence,
    FileLocation,
    ImportReference,
    SymbolReference,
)
from .file_contribution import FileContribution
from .graphs import (
    CallEdge,
    CallGraph,
    ReferenceEdge,
    ReferenceGraph,
    TypeRelationshipEdge,
    TypeRelationshipGraph,
)
from .persistence import (
    PersistenceModel,
    PersistenceModelKind,
    RepositoryMethod,
    RepositoryMethodKind,
)
from .repository_graph import RepositoryGraph
from .repository_index import (
    CallEntry,
    ConfigEntry,
    EntrypointEntry,
    EventEntry,
    FileIndex,
    ImportEntry,
    PersistenceEntry,
    RawReference,
    RepositoryIndex,
    RepositoryMethodEntry,
    SymbolEntry,
    TestEntry,
    TypeRelationshipEntry,
)
from .repository_model import (
    AsyncEntryPoint,
    EntryPoint,
    EntryPointKind,
    RepositoryModel,
)
from .symbol import Symbol, SymbolKind, SymbolVisibility
from .tests import TestDefinition, TestFixture, TestFramework

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
    # Repository Index (IR)
    "RepositoryIndex",
    "FileIndex",
    "SymbolEntry",
    "ImportEntry",
    "RawReference",
    "CallEntry",
    "EntrypointEntry",
    "TypeRelationshipEntry",
    "PersistenceEntry",
    "RepositoryMethodEntry",
    "EventEntry",
    "TestEntry",
    "ConfigEntry",
    # Incremental Compilation Graph
    "FileContribution",
    "RepositoryGraph",
]

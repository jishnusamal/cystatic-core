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
    "AnnotationReference",
    "AsyncEntryPoint",
    # Graphs
    "CallEdge",
    "CallEntry",
    "CallGraph",
    "CallReference",
    "ConfigEntry",
    "ConfigReferenceKind",
    # Configuration
    "ConfigurationReference",
    "EntryPoint",
    "EntryPointKind",
    "EntrypointEntry",
    # Events
    "EventConstruct",
    "EventEntry",
    "EventOperationKind",
    # Evidence
    "Evidence",
    # Incremental Compilation Graph
    "FileContribution",
    "FileIndex",
    "FileLocation",
    "ImportEntry",
    "ImportReference",
    "PersistenceEntry",
    # Persistence
    "PersistenceModel",
    "PersistenceModelKind",
    "RawReference",
    "ReferenceEdge",
    "ReferenceGraph",
    "RepositoryGraph",
    # Repository Index (IR)
    "RepositoryIndex",
    "RepositoryMethod",
    "RepositoryMethodEntry",
    "RepositoryMethodKind",
    # Repository Model
    "RepositoryModel",
    # Symbol
    "Symbol",
    "SymbolEntry",
    "SymbolKind",
    "SymbolReference",
    "SymbolVisibility",
    # Tests
    "TestDefinition",
    "TestEntry",
    "TestFixture",
    "TestFramework",
    "TypeRelationshipEdge",
    "TypeRelationshipEntry",
    "TypeRelationshipGraph",
]

"""Repository graph - the patchable, long-lived representation of a code repository."""

import pickle
from dataclasses import dataclass, field
from typing import Any

from .symbol import Symbol
from .graphs import CallGraph, ReferenceGraph, TypeRelationshipGraph
from .repository_model import RepositoryModel, EntryPoint, AsyncEntryPoint
from .persistence import PersistenceModel, RepositoryMethod
from .events import EventConstruct
from .tests import TestDefinition
from .configuration import ConfigurationReference
from .file_contribution import FileContribution


@dataclass
class RepositoryGraph:
    """
    The patchable repository graph.

    Maintains file contributions and compiled global indexes. It serves
    as a long-lived serializable database that can be patched with diffs.
    """
    files: dict[str, FileContribution] = field(default_factory=dict)
    symbols: dict[str, Symbol] = field(default_factory=dict)
    imports: dict[str, Symbol] = field(default_factory=dict)
    call_graph: CallGraph = field(default_factory=lambda: CallGraph())
    reference_graph: ReferenceGraph = field(default_factory=lambda: ReferenceGraph())
    type_relationship_graph: TypeRelationshipGraph = field(default_factory=lambda: TypeRelationshipGraph())
    entry_points: tuple[EntryPoint, ...] = field(default_factory=tuple)
    async_entry_points: tuple[AsyncEntryPoint, ...] = field(default_factory=tuple)
    persistence_models: tuple[PersistenceModel, ...] = field(default_factory=tuple)
    repository_methods: tuple[RepositoryMethod, ...] = field(default_factory=tuple)
    event_constructs: tuple[EventConstruct, ...] = field(default_factory=tuple)
    test_definitions: tuple[TestDefinition, ...] = field(default_factory=tuple)
    configuration_references: tuple[ConfigurationReference, ...] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_model(self) -> RepositoryModel:
        """Convert to the immutable RepositoryModel expected by downstream compilers."""
        all_symbols = frozenset(self.symbols.values()) | frozenset(self.imports.values())
        return RepositoryModel(
            symbols=all_symbols,
            call_graph=self.call_graph,
            reference_graph=self.reference_graph,
            type_relationship_graph=self.type_relationship_graph,
            entry_points=self.entry_points,
            async_entry_points=self.async_entry_points,
            persistence_models=self.persistence_models,
            repository_methods=self.repository_methods,
            event_constructs=self.event_constructs,
            test_definitions=self.test_definitions,
            configuration_references=self.configuration_references,
            metadata=self.metadata,
        )

    def to_bytes(self) -> bytes:
        """Serialize the RepositoryGraph using pickle."""
        return pickle.dumps(self)

    @classmethod
    def from_bytes(cls, data: bytes) -> "RepositoryGraph":
        """Deserialize the RepositoryGraph using pickle."""
        return pickle.loads(data)

    def save_to_file(self, file_path: str) -> None:
        """Save the RepositoryGraph to a file on disk."""
        with open(file_path, "wb") as f:
            f.write(self.to_bytes())

    @classmethod
    def load_from_file(cls, file_path: str) -> "RepositoryGraph":
        """Load the RepositoryGraph from a file on disk."""
        with open(file_path, "rb") as f:
            return cls.from_bytes(f.read())

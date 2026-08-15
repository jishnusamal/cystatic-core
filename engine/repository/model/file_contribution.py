"""File contribution - structural facts owned by a single source file."""

from dataclasses import dataclass, field
from typing import Any

import sys

from .repository_index import (
    CallEntry,
    ConfigEntry,
    EntrypointEntry,
    EventEntry,
    FileIndex,
    ImportEntry,
    PersistenceEntry,
    RawReference,
    RepositoryMethodEntry,
    SymbolEntry,
    TestEntry,
    TypeRelationshipEntry,
)


@dataclass(slots=True, frozen=True)
class FileContribution:
    """
    Represents the structural facts owned by a single source file.

    This matches the structure of FileIndex but is named as a contribution
    to the patchable RepositoryGraph.
    """
    file_path: str
    language: str
    symbols: tuple[SymbolEntry, ...] = field(default_factory=tuple)
    imports: tuple[ImportEntry, ...] = field(default_factory=tuple)
    references: tuple[RawReference, ...] = field(default_factory=tuple)
    calls: tuple[CallEntry, ...] = field(default_factory=tuple)
    entrypoints: tuple[EntrypointEntry, ...] = field(default_factory=tuple)
    type_relationships: tuple[TypeRelationshipEntry, ...] = field(default_factory=tuple)
    persistence_models: tuple[PersistenceEntry, ...] = field(default_factory=tuple)
    repository_methods: tuple[RepositoryMethodEntry, ...] = field(default_factory=tuple)
    events: tuple[EventEntry, ...] = field(default_factory=tuple)
    tests: tuple[TestEntry, ...] = field(default_factory=tuple)
    configurations: tuple[ConfigEntry, ...] = field(default_factory=tuple)
    source_hash: str = ""

    def __post_init__(self):
        """Intern string fields after initialization."""
        object.__setattr__(self, 'file_path', sys.intern(self.file_path))
        object.__setattr__(self, 'language', sys.intern(self.language))
        if self.source_hash:
            object.__setattr__(self, 'source_hash', sys.intern(self.source_hash))

    @classmethod
    def from_file_index(cls, file_index: FileIndex, source_hash: str = "") -> "FileContribution":
        """Create a FileContribution from a FileIndex."""
        return cls(
            file_path=file_index.path,
            language=file_index.language,
            symbols=file_index.symbols,
            imports=file_index.imports,
            references=file_index.references,
            calls=file_index.calls,
            entrypoints=file_index.entrypoints,
            type_relationships=file_index.type_relationships,
            persistence_models=file_index.persistence_models,
            repository_methods=file_index.repository_methods,
            events=file_index.events,
            tests=file_index.tests,
            configurations=file_index.configurations,
            source_hash=source_hash,
        )

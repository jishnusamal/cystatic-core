"""Backward-compatibility shim. Import from engine.repository.indexing instead."""

from engine.repository.indexing.repository_store import (
    FilesystemRepositoryStore,
    MemoryRepositoryStore,
    RepositoryStore,
)

__all__ = [
    "RepositoryStore",
    "FilesystemRepositoryStore",
    "MemoryRepositoryStore",
]

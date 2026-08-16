"""Storage and streaming indexing abstractions for repository models."""

from engine.repository.indexing.compatibility import (
    FactsToIndexAdapter,
)
from engine.repository.indexing.indexer import (
    RepositoryIndexer,
)
from engine.repository.indexing.repository_store import (
    FilesystemRepositoryStore,
    MemoryRepositoryStore,
    RepositoryStore,
)
from engine.repository.indexing.sink import (
    InMemoryFactSink,
    RepositoryFactSink,
)

__all__ = [
    "FactsToIndexAdapter",
    "FilesystemRepositoryStore",
    "InMemoryFactSink",
    "MemoryRepositoryStore",
    "RepositoryFactSink",
    "RepositoryIndexer",
    "RepositoryStore",
]

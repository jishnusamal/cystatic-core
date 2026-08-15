"""Storage and streaming indexing abstractions for repository models."""

from engine.repository.indexing.repository_store import (
    FilesystemRepositoryStore,
    MemoryRepositoryStore,
    RepositoryStore,
)
from engine.repository.indexing.sink import (
    RepositoryFactSink,
    InMemoryFactSink,
)
from engine.repository.indexing.indexer import (
    RepositoryIndexer,
)
from engine.repository.indexing.compatibility import (
    FactsToIndexAdapter,
)

__all__ = [
    "RepositoryStore",
    "FilesystemRepositoryStore",
    "MemoryRepositoryStore",
    "RepositoryFactSink",
    "InMemoryFactSink",
    "RepositoryIndexer",
    "FactsToIndexAdapter",
]

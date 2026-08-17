"""Base integration interfaces.

All integrations must implement these interfaces.
"""

from .event_provider import EventProvider
from .installation_provider import InstallationProvider
from .output_provider import OutputProvider
from .repository_provider import (
    RepositoryProvider,
    RepositoryCommit,
    RepositoryTreeEntry,
    RepositoryBlob,
    RepositoryAcquisitionMode,
)

__all__ = [
    "EventProvider",
    "InstallationProvider",
    "OutputProvider",
    "RepositoryProvider",
    "RepositoryCommit",
    "RepositoryTreeEntry",
    "RepositoryBlob",
    "RepositoryAcquisitionMode",
]

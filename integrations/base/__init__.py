"""Base integration interfaces.

All integrations must implement these interfaces.
"""

from .event_provider import EventProvider
from .installation_provider import InstallationProvider
from .output_provider import OutputProvider
from .repository_provider import (
    RepositoryAcquisitionMode,
    RepositoryBlob,
    RepositoryCommit,
    RepositoryProvider,
    RepositoryTreeEntry,
)

__all__ = [
    "EventProvider",
    "InstallationProvider",
    "OutputProvider",
    "RepositoryAcquisitionMode",
    "RepositoryBlob",
    "RepositoryCommit",
    "RepositoryProvider",
    "RepositoryTreeEntry",
]

"""Base integration interfaces.

All integrations must implement these interfaces.
"""

from .repository_provider import RepositoryProvider
from .event_provider import EventProvider
from .installation_provider import InstallationProvider
from .output_provider import OutputProvider

__all__ = [
    "EventProvider",
    "InstallationProvider",
    "OutputProvider",
    "RepositoryProvider",
]
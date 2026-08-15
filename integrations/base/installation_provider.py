"""Installation provider interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class InstallationProvider(ABC):
    """Responsible for authentication.

    The pipeline never deals with JWTs or OAuth.
    """

    @abstractmethod
    async def installation(self, installation_id: str) -> dict[str, Any]:
        """Get installation information.

        Args:
            installation_id: Installation identifier

        Returns:
            Installation information
        """
        pass

    @abstractmethod
    async def authenticate(self, installation_id: str) -> str:
        """Get an authentication token for the installation.

        Args:
            installation_id: Installation identifier

        Returns:
            Authentication token
        """
        pass

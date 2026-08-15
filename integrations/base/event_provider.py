"""Event provider interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from models.analysis import AnalysisRequest, AnalysisTrigger


class EventProvider(ABC):
    """Responsible for receiving events.

    Outputs a language-independent event.
    No GitHub-specific payloads leave this layer.
    """

    @abstractmethod
    async def verify(
        self, payload: bytes, signature: str | None, secret: str | None
    ) -> bool:
        """Verify the event signature.

        Args:
            payload: Raw event payload
            signature: Event signature
            secret: Verification secret

        Returns:
            True if signature is valid
        """
        pass

    @abstractmethod
    async def parse(self, payload: dict[str, Any]) -> AnalysisRequest:
        """Parse the event payload into an AnalysisRequest.

        Args:
            payload: Event payload (platform-agnostic)

        Returns:
            AnalysisRequest object
        """
        pass

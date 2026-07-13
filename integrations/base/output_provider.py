"""Output provider interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from operational.model import OperationalChangeModel


class OutputProvider(ABC):
    """Responsible for delivering results.
    
    Examples:
    - GitHub -> PR comment
    - Slack -> Message
    - Dashboard -> Analysis page
    """
    
    @abstractmethod
    async def publish(
        self,
        ocm: OperationalChangeModel,
        destination: dict[str, Any],
    ) -> str | None:
        """Publish the analysis result.
        
        Args:
            ocm: Operational change model
            destination: Destination information (e.g., PR number, channel ID)
            
        Returns:
            Published content identifier (e.g., comment ID) or None
        """
        pass
    
    @abstractmethod
    async def update(
        self,
        ocm: OperationalChangeModel,
        destination: dict[str, Any],
        previous_id: str | None,
    ) -> str | None:
        """Update a previously published result.
        
        Args:
            ocm: Operational change model
            destination: Destination information
            previous_id: Previous published content identifier
            
        Returns:
            Updated content identifier or None
        """
        pass
    
    @abstractmethod
    async def delete(
        self,
        destination: dict[str, Any],
        content_id: str,
    ) -> None:
        """Delete a previously published result.
        
        Args:
            destination: Destination information
            content_id: Published content identifier
        """
        pass
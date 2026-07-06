"""Connect stage - builds relationships between groups."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from core_engine.graph import ConnectedGraph, GroupedGraph, GroupEdge


@runtime_checkable
class ConnectionRule(Protocol):
    """Protocol for connection rules."""
    
    def connect(
        self,
        groups: dict[str, any],
        graph,
    ) -> list[GroupEdge]:
        """Build relationships between groups.
        
        Args:
            groups: Dictionary of group ID to ChangeGroup
            graph: The grouped graph for context
            
        Returns:
            List of GroupEdge objects representing relationships
        """
        ...
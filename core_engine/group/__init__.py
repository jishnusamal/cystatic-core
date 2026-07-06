"""Group stage - collapses nodes into semantic units."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from language_adapters.ir.nodes import BaseNode
from core_engine.graph import FilteredGraph, GroupedGraph, ChangeGroup


@runtime_checkable
class GroupStrategy(Protocol):
    """Protocol for grouping strategies."""
    
    def assign_group(
        self,
        node: BaseNode,
        graph: FilteredGraph,
    ) -> str | None:
        """Assign a node to a group.
        
        Args:
            node: The node to group
            graph: The filtered graph for context
            
        Returns:
            Group ID if the node should be grouped, None to leave ungrouped
        """
        ...
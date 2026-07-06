"""Filter stage - removes low-value graph information."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from language_adapters.ir.nodes import BaseNode
from language_adapters.ir.edges import BaseEdge


@runtime_checkable
class FilterRule(Protocol):
    """Protocol for filter rules."""
    
    def keep_node(
        self,
        node: BaseNode,
        graph: SemanticGraph,
    ) -> bool:
        """Determine if a node should be kept.
        
        Args:
            node: The node to evaluate
            graph: The full semantic graph for context
            
        Returns:
            True if the node should be kept, False to remove
        """
        ...
    
    def keep_edge(
        self,
        edge: BaseEdge,
        graph: SemanticGraph,
    ) -> bool:
        """Determine if an edge should be kept.
        
        Args:
            edge: The edge to evaluate
            graph: The full semantic graph for context
            
        Returns:
            True if the edge should be kept, False to remove
        """
        ...


# Import here to avoid circular imports
from language_adapters.ir.semantic_graph import SemanticGraph  # noqa: E402

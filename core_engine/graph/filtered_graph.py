"""FilteredGraph - output of the Filter stage."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Set

from language_adapters.ir.semantic_graph import SemanticGraph
from language_adapters.ir.nodes import BaseNode
from language_adapters.ir.edges import BaseEdge


@dataclass
class FilteredGraph:
    """Output of the Filter stage.
    
    Contains only nodes and edges that passed all filter rules.
    """
    
    nodes: Dict[str, BaseNode] = field(default_factory=dict)
    edges: List[BaseEdge] = field(default_factory=list)
    file_paths: Set[str] = field(default_factory=set)
    removed_nodes: List[BaseNode] = field(default_factory=list)
    removed_edges: List[BaseEdge] = field(default_factory=list)
    
    @classmethod
    def from_semantic_graph(cls, graph: SemanticGraph) -> FilteredGraph:
        """Create a FilteredGraph from a SemanticGraph."""
        return cls(
            nodes=dict(graph.nodes),
            edges=list(graph.edges),
            file_paths=set(graph.file_paths),
        )
    
    def to_semantic_graph(self) -> SemanticGraph:
        """Convert back to SemanticGraph."""
        return SemanticGraph(
            nodes=dict(self.nodes),
            edges=list(self.edges),
            file_paths=set(self.file_paths),
        )
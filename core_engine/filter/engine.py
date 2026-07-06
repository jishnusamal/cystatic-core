"""Filter engine - applies filter rules to remove low-value graph information."""

from __future__ import annotations

from typing import List

from language_adapters.ir.semantic_graph import SemanticGraph
from language_adapters.ir.nodes import BaseNode
from language_adapters.ir.edges import BaseEdge

from core_engine.graph import FilteredGraph
from core_engine.filter.registry import FilterRegistry


class FilterEngine:
    """Engine that applies filter rules to a semantic graph.
    
    The engine iterates through all nodes and edges, asking each registered
    rule whether to keep them. If any rule rejects a node/edge, it is removed.
    """
    
    def __init__(self, registry: FilterRegistry):
        """Initialize the filter engine.
        
        Args:
            registry: Registry containing filter rules to apply
        """
        self.registry = registry
    
    def run(self, graph: SemanticGraph) -> FilteredGraph:
        """Apply all filter rules to the graph.
        
        Args:
            graph: The semantic graph to filter
            
        Returns:
            FilteredGraph containing only nodes and edges that passed all rules
        """
        filtered = FilteredGraph.from_semantic_graph(graph)
        rules = self.registry.get_rules()
        
        # Filter nodes
        nodes_to_remove = []
        for node_key, node in filtered.nodes.items():
            # Ask every rule - if any rule rejects, remove the node
            should_keep = True
            for rule in rules:
                if not rule.keep_node(node, graph):
                    should_keep = False
                    break
            
            if not should_keep:
                nodes_to_remove.append(node)
        
        # Remove rejected nodes
        for node in nodes_to_remove:
            filtered.nodes.pop(self._node_key(node), None)
            filtered.removed_nodes.append(node)
        
        # Filter edges - only keep edges where both endpoints are kept
        edges_to_remove = []
        for edge in filtered.edges:
            # Check if both source and target nodes are still in the graph
            source_key = self._node_key(edge.source)
            target_key = self._node_key(edge.target)
            
            if source_key not in filtered.nodes or target_key not in filtered.nodes:
                edges_to_remove.append(edge)
                continue
            
            # Ask every rule - if any rule rejects, remove the edge
            should_keep = True
            for rule in rules:
                if not rule.keep_edge(edge, graph):
                    should_keep = False
                    break
            
            if not should_keep:
                edges_to_remove.append(edge)
        
        # Remove rejected edges
        for edge in edges_to_remove:
            filtered.edges.remove(edge)
            filtered.removed_edges.append(edge)
        
        # Update file_paths to only include kept nodes
        filtered.file_paths = {node.file_path for node in filtered.nodes.values()}
        
        return filtered
    
    @staticmethod
    def _node_key(node: BaseNode) -> str:
        """Generate a unique key for a node."""
        if hasattr(node, 'class_name') and node.node_type.name == "METHOD":
            return f"{node.node_type.name}:{node.name}:{node.class_name}:{node.file_path}"
        return f"{node.node_type.name}:{node.name}:{node.file_path}"
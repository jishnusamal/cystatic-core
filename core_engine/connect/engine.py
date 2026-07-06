"""Connect engine - builds relationships between groups."""

from __future__ import annotations

from typing import List

from language_adapters.ir.nodes import BaseNode
from language_adapters.ir.edges import BaseEdge

from core_engine.graph import GroupedGraph, ConnectedGraph, GroupEdge, ChangeGroup
from core_engine.connect.registry import ConnectionRegistry


class ConnectEngine:
    """Engine that builds relationships between groups.
    
    The engine applies each registered connection rule to aggregate
    existing graph edges into group-level relationships.
    """
    
    def __init__(self, registry: ConnectionRegistry):
        """Initialize the connect engine.
        
        Args:
            registry: Registry containing connection rules to apply
        """
        self.registry = registry
    
    def run(self, grouped_graph: GroupedGraph) -> ConnectedGraph:
        """Apply all connection rules to build group relationships.
        
        Args:
            grouped_graph: The grouped graph to connect
            
        Returns:
            ConnectedGraph containing groups with relationships between them
        """
        connected = ConnectedGraph()
        connected.groups = dict(grouped_graph.groups)
        connected.file_paths = set(grouped_graph.file_paths)
        
        rules = self.registry.get_rules()
        
        # Apply each rule to build relationships
        all_edges = []
        for rule in rules:
            edges = rule.connect(connected.groups, grouped_graph)
            all_edges.extend(edges)
        
        # Deduplicate edges
        seen = set()
        unique_edges = []
        for edge in all_edges:
            edge_key = (edge.source_group_id, edge.target_group_id, edge.edge_type)
            if edge_key not in seen:
                seen.add(edge_key)
                unique_edges.append(edge)
        
        connected.group_edges = unique_edges
        
        return connected
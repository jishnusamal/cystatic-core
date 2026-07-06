"""Group engine - collapses nodes into semantic units."""

from __future__ import annotations

from typing import List

from language_adapters.ir.nodes import BaseNode
from language_adapters.ir.edges import BaseEdge

from core_engine.graph import FilteredGraph, GroupedGraph, ChangeGroup
from core_engine.group.registry import GroupRegistry


class GroupEngine:
    """Engine that groups related nodes into semantic units.
    
    The engine applies each registered strategy to every node,
    assigning it to a group based on the first matching strategy.
    """
    
    def __init__(self, registry: GroupRegistry):
        """Initialize the group engine.
        
        Args:
            registry: Registry containing grouping strategies to apply
        """
        self.registry = registry
    
    def run(self, filtered_graph: FilteredGraph) -> GroupedGraph:
        """Apply all grouping strategies to the graph.
        
        Args:
            filtered_graph: The filtered graph to group
            
        Returns:
            GroupedGraph containing semantic groups of nodes
        """
        grouped = GroupedGraph()
        grouped.file_paths = set(filtered_graph.file_paths)
        
        strategies = self.registry.get_strategies()
        
        # Group nodes
        for node in filtered_graph.nodes.values():
            group_id = None
            
            # Try each strategy until one assigns a group
            for strategy in strategies:
                group_id = strategy.assign_group(node, filtered_graph)
                if group_id is not None:
                    break
            
            if group_id is not None:
                # Add node to group
                if group_id not in grouped.groups:
                    grouped.groups[group_id] = ChangeGroup(
                        id=group_id,
                        type=self._infer_group_type(node),
                        title=self._infer_group_title(node),
                    )
                
                grouped.groups[group_id].nodes.append(node)
            else:
                # Leave node ungrouped
                grouped.ungrouped_nodes[self._node_key(node)] = node
        
        # Group edges - only keep edges where both endpoints are in the same group
        # or both are in different groups
        edges_to_keep = []
        for edge in filtered_graph.edges:
            # Skip edges with missing endpoints
            if edge.source is None or edge.target is None:
                continue
                
            source_key = self._node_key(edge.source)
            target_key = self._node_key(edge.target)
            
            # Find which groups the endpoints belong to
            source_group = self._find_node_group(edge.source, grouped)
            target_group = self._find_node_group(edge.target, grouped)
            
            if source_group is not None and target_group is not None:
                # Both endpoints are in groups
                if source_group == target_group:
                    # Intra-group edge - add to group
                    grouped.groups[source_group].edges.append(edge)
                else:
                    # Inter-group edge - keep for connection stage
                    edges_to_keep.append(edge)
            elif source_group is not None or target_group is not None:
                # One endpoint is in a group, one is not - keep edge
                edges_to_keep.append(edge)
            else:
                # Both endpoints are ungrouped - keep edge
                edges_to_keep.append(edge)
        
        grouped.ungrouped_edges = edges_to_keep
        
        return grouped
    
    def _find_node_group(self, node: BaseNode, grouped: GroupedGraph) -> str | None:
        """Find which group a node belongs to.
        
        Args:
            node: The node to find
            grouped: The grouped graph
            
        Returns:
            Group ID if found, None otherwise
        """
        node_key = self._node_key(node)
        for group_id, group in grouped.groups.items():
            for group_node in group.nodes:
                if self._node_key(group_node) == node_key:
                    return group_id
        return None
    
    def _infer_group_type(self, node: BaseNode) -> str:
        """Infer the group type from a node.
        
        Args:
            node: The node to infer type from
            
        Returns:
            Group type string
        """
        if node.node_type is None:
            return 'service'
            
        type_mapping = {
            'ENDPOINT': 'endpoint',
            'MODEL': 'model',
            'MIGRATION': 'migration',
            'TEST': 'test',
            'TRANSACTION': 'transaction',
            'QUERY': 'query',
            'EXTERNAL_SERVICE': 'external_service',
            'CACHE': 'cache',
            'QUEUE': 'queue',
            'EVENT': 'event',
        }
        return type_mapping.get(node.node_type.name, 'service')
    
    def _infer_group_title(self, node: BaseNode) -> str:
        """Infer a human-readable title for a group from a node.
        
        Args:
            node: The node to infer title from
            
        Returns:
            Group title string
        """
        # Use the node name as the title
        name = node.name
        
        # Clean up common patterns
        if node.node_type is not None and node.node_type.name == 'ENDPOINT':
            # Format as "METHOD /route"
            method = node.properties.get('method', '')
            route = node.properties.get('route', name)
            if method:
                return f"{method} {route}"
        elif node.node_type is not None and node.node_type.name == 'MODEL':
            return f"{name} Model"
        elif node.node_type is not None and node.node_type.name == 'MIGRATION':
            return f"Migration: {name}"
        elif node.node_type is not None and node.node_type.name == 'TEST':
            return f"Test: {name}"
        
        return name
    
    @staticmethod
    def _node_key(node: BaseNode) -> str:
        """Generate a unique key for a node."""
        if hasattr(node, 'class_name') and node.node_type is not None and node.node_type.name == "METHOD":
            return f"{node.node_type.name}:{node.name}:{node.class_name}:{node.file_path}"
        return f"{node.node_type.name if node.node_type else 'UNKNOWN'}:{node.name}:{node.file_path}"

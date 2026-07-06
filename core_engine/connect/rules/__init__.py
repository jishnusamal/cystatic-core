"""Connection rules for building relationships between groups."""

from __future__ import annotations

from typing import List

from language_adapters.ir.edges import EdgeType

from core_engine.connect import ConnectionRule
from core_engine.graph import GroupedGraph, GroupEdge


class CallConnectionRule:
    """Build relationships based on CALLS edges."""
    
    def connect(self, groups: dict, graph: GroupedGraph) -> List[GroupEdge]:
        """Aggregate CALLS edges into group relationships.
        
        Args:
            groups: Dictionary of group ID to ChangeGroup
            graph: The grouped graph for context
            
        Returns:
            List of GroupEdge objects
        """
        edges = []
        
        # Build a mapping from node to group
        node_to_group = {}
        for group_id, group in groups.items():
            for node in group.nodes:
                node_key = self._node_key(node)
                node_to_group[node_key] = group_id
        
        # Find all CALLS edges and create group relationships
        for edge in graph.ungrouped_edges:
            if edge.edge_type == EdgeType.CALLS:
                source_key = self._node_key(edge.source)
                target_key = self._node_key(edge.target)
                
                source_group = node_to_group.get(source_key)
                target_group = node_to_group.get(target_key)
                
                if source_group and target_group and source_group != target_group:
                    edges.append(GroupEdge(
                        source_group_id=source_group,
                        target_group_id=target_group,
                        edge_type="calls",
                    ))
        
        return edges
    
    @staticmethod
    def _node_key(node) -> str:
        """Generate a unique key for a node."""
        if hasattr(node, 'class_name') and node.node_type.name == "METHOD":
            return f"{node.node_type.name}:{node.name}:{node.class_name}:{node.file_path}"
        return f"{node.node_type.name}:{node.name}:{node.file_path}"


class PersistenceConnectionRule:
    """Build relationships based on persistence edges (WRITES, READS, etc.)."""
    
    def connect(self, groups: dict, graph: GroupedGraph) -> List[GroupEdge]:
        """Aggregate persistence edges into group relationships.
        
        Args:
            groups: Dictionary of group ID to ChangeGroup
            graph: The grouped graph for context
            
        Returns:
            List of GroupEdge objects
        """
        edges = []
        
        # Build a mapping from node to group
        node_to_group = {}
        for group_id, group in groups.items():
            for node in group.nodes:
                node_key = self._node_key(node)
                node_to_group[node_key] = group_id
        
        # Find all persistence edges
        persistence_types = {
            EdgeType.WRITES, EdgeType.READS, EdgeType.CREATES,
            EdgeType.UPDATES, EdgeType.DELETES
        }
        
        for edge in graph.ungrouped_edges:
            if edge.edge_type in persistence_types:
                source_key = self._node_key(edge.source)
                target_key = self._node_key(edge.target)
                
                source_group = node_to_group.get(source_key)
                target_group = node_to_group.get(target_key)
                
                if source_group and target_group and source_group != target_group:
                    edges.append(GroupEdge(
                        source_group_id=source_group,
                        target_group_id=target_group,
                        edge_type="persistence",
                        properties={"operation": edge.edge_type.name.lower()},
                    ))
        
        return edges
    
    @staticmethod
    def _node_key(node) -> str:
        """Generate a unique key for a node."""
        if hasattr(node, 'class_name') and node.node_type.name == "METHOD":
            return f"{node.node_type.name}:{node.name}:{node.class_name}:{node.file_path}"
        return f"{node.node_type.name}:{node.name}:{node.file_path}"


class ValidationConnectionRule:
    """Build relationships based on VALIDATES edges."""
    
    def connect(self, groups: dict, graph: GroupedGraph) -> List[GroupEdge]:
        """Aggregate validation edges into group relationships.
        
        Args:
            groups: Dictionary of group ID to ChangeGroup
            graph: The grouped graph for context
            
        Returns:
            List of GroupEdge objects
        """
        edges = []
        
        # Build a mapping from node to group
        node_to_group = {}
        for group_id, group in groups.items():
            for node in group.nodes:
                node_key = self._node_key(node)
                node_to_group[node_key] = group_id
        
        # Find all VALIDATES edges
        for edge in graph.ungrouped_edges:
            if edge.edge_type == EdgeType.VALIDATES:
                source_key = self._node_key(edge.source)
                target_key = self._node_key(edge.target)
                
                source_group = node_to_group.get(source_key)
                target_group = node_to_group.get(target_key)
                
                if source_group and target_group and source_group != target_group:
                    edges.append(GroupEdge(
                        source_group_id=source_group,
                        target_group_id=target_group,
                        edge_type="validates",
                    ))
        
        return edges
    
    @staticmethod
    def _node_key(node) -> str:
        """Generate a unique key for a node."""
        if hasattr(node, 'class_name') and node.node_type.name == "METHOD":
            return f"{node.node_type.name}:{node.name}:{node.class_name}:{node.file_path}"
        return f"{node.node_type.name}:{node.name}:{node.file_path}"


class MigrationConnectionRule:
    """Build relationships based on MIGRATES edges."""
    
    def connect(self, groups: dict, graph: GroupedGraph) -> List[GroupEdge]:
        """Aggregate migration edges into group relationships.
        
        Args:
            groups: Dictionary of group ID to ChangeGroup
            graph: The grouped graph for context
            
        Returns:
            List of GroupEdge objects
        """
        edges = []
        
        # Build a mapping from node to group
        node_to_group = {}
        for group_id, group in groups.items():
            for node in group.nodes:
                node_key = self._node_key(node)
                node_to_group[node_key] = group_id
        
        # Find all MIGRATES edges
        for edge in graph.ungrouped_edges:
            if edge.edge_type == EdgeType.MIGRATES:
                source_key = self._node_key(edge.source)
                target_key = self._node_key(edge.target)
                
                source_group = node_to_group.get(source_key)
                target_group = node_to_group.get(target_key)
                
                if source_group and target_group and source_group != target_group:
                    edges.append(GroupEdge(
                        source_group_id=source_group,
                        target_group_id=target_group,
                        edge_type="migrates",
                    ))
        
        return edges
    
    @staticmethod
    def _node_key(node) -> str:
        """Generate a unique key for a node."""
        if hasattr(node, 'class_name') and node.node_type.name == "METHOD":
            return f"{node.node_type.name}:{node.name}:{node.class_name}:{node.file_path}"
        return f"{node.node_type.name}:{node.name}:{node.file_path}"


class TransactionConnectionRule:
    """Build relationships based on transaction boundaries."""
    
    def connect(self, groups: dict, graph: GroupedGraph) -> List[GroupEdge]:
        """Aggregate transaction edges into group relationships.
        
        Args:
            groups: Dictionary of group ID to ChangeGroup
            graph: The grouped graph for context
            
        Returns:
            List of GroupEdge objects
        """
        edges = []
        
        # Build a mapping from node to group
        node_to_group = {}
        for group_id, group in groups.items():
            for node in group.nodes:
                node_key = self._node_key(node)
                node_to_group[node_key] = group_id
        
        # Find transaction nodes and connect them to related groups
        for group_id, group in groups.items():
            if group.type == "transaction":
                # Connect transaction to all groups that have nodes in the same file
                for node in group.nodes:
                    node_key = self._node_key(node)
                    for other_group_id, other_group in groups.items():
                        if other_group_id != group_id:
                            for other_node in other_group.nodes:
                                if other_node.file_path == node.file_path:
                                    edges.append(GroupEdge(
                                        source_group_id=group_id,
                                        target_group_id=other_group_id,
                                        edge_type="transaction",
                                    ))
                                    break
        
        return edges
    
    @staticmethod
    def _node_key(node) -> str:
        """Generate a unique key for a node."""
        if hasattr(node, 'class_name') and node.node_type.name == "METHOD":
            return f"{node.node_type.name}:{node.name}:{node.class_name}:{node.file_path}"
        return f"{node.node_type.name}:{node.name}:{node.file_path}"


class QueryConnectionRule:
    """Build relationships based on query operations."""
    
    def connect(self, groups: dict, graph: GroupedGraph) -> List[GroupEdge]:
        """Aggregate query edges into group relationships.
        
        Args:
            groups: Dictionary of group ID to ChangeGroup
            graph: The grouped graph for context
            
        Returns:
            List of GroupEdge objects
        """
        edges = []
        
        # Build a mapping from node to group
        node_to_group = {}
        for group_id, group in groups.items():
            for node in group.nodes:
                node_key = self._node_key(node)
                node_to_group[node_key] = group_id
        
        # Find all query-related edges
        for edge in graph.ungrouped_edges:
            if edge.edge_type in (EdgeType.READS, EdgeType.USES):
                source_key = self._node_key(edge.source)
                target_key = self._node_key(edge.target)
                
                source_group = node_to_group.get(source_key)
                target_group = node_to_group.get(target_key)
                
                if source_group and target_group and source_group != target_group:
                    edges.append(GroupEdge(
                        source_group_id=source_group,
                        target_group_id=target_group,
                        edge_type="query",
                    ))
        
        return edges
    
    @staticmethod
    def _node_key(node) -> str:
        """Generate a unique key for a node."""
        if hasattr(node, 'class_name') and node.node_type.name == "METHOD":
            return f"{node.node_type.name}:{node.name}:{node.class_name}:{node.file_path}"
        return f"{node.node_type.name}:{node.name}:{node.file_path}"


class EndpointConnectionRule:
    """Build relationships based on endpoint exposure."""
    
    def connect(self, groups: dict, graph: GroupedGraph) -> List[GroupEdge]:
        """Aggregate endpoint edges into group relationships.
        
        Args:
            groups: Dictionary of group ID to ChangeGroup
            graph: The grouped graph for context
            
        Returns:
            List of GroupEdge objects
        """
        edges = []
        
        # Build a mapping from node to group
        node_to_group = {}
        for group_id, group in groups.items():
            for node in group.nodes:
                node_key = self._node_key(node)
                node_to_group[node_key] = group_id
        
        # Find all EXPOSES edges
        for edge in graph.ungrouped_edges:
            if edge.edge_type == EdgeType.EXPOSES:
                source_key = self._node_key(edge.source)
                target_key = self._node_key(edge.target)
                
                source_group = node_to_group.get(source_key)
                target_group = node_to_group.get(target_key)
                
                if source_group and target_group and source_group != target_group:
                    edges.append(GroupEdge(
                        source_group_id=source_group,
                        target_group_id=target_group,
                        edge_type="exposes",
                    ))
        
        return edges
    
    @staticmethod
    def _node_key(node) -> str:
        """Generate a unique key for a node."""
        if hasattr(node, 'class_name') and node.node_type.name == "METHOD":
            return f"{node.node_type.name}:{node.name}:{node.class_name}:{node.file_path}"
        return f"{node.node_type.name}:{node.name}:{node.file_path}"
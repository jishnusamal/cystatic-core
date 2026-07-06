"""Summarize stage - builds ReasoningPacket from ConnectedGraph."""

from __future__ import annotations

from typing import Dict, List, Any

from language_adapters.ir.nodes import BaseNode, NodeType
from language_adapters.ir.edges import BaseEdge, EdgeType

from core_engine.graph import ConnectedGraph, GroupEdge, ChangeGroup, ReasoningPacket


class PacketBuilder:
    """Builds a ReasoningPacket from a ConnectedGraph.
    
    This is the only object the LLM sees. It's a compact, high-signal
    representation instead of thousands of raw graph nodes and edges.
    """
    
    def build(self, connected: ConnectedGraph) -> ReasoningPacket:
        """Build a ReasoningPacket from a ConnectedGraph.
        
        Args:
            connected: The connected graph to summarize
            
        Returns:
            ReasoningPacket containing compact representation
        """
        packet = ReasoningPacket()
        
        # Build summary
        packet.summary = self._build_summary(connected)
        
        # Extract changed areas
        packet.changed_areas = self._extract_changed_areas(connected)
        
        # Extract semantic changes
        packet.semantic_changes = self._extract_semantic_changes(connected)
        
        # Extract relationships
        packet.relationships = self._extract_relationships(connected)
        
        # Extract migrations
        packet.migrations = self._extract_migrations(connected)
        
        # Extract validations
        packet.validations = self._extract_validations(connected)
        
        # Extract persistence changes
        packet.persistence = self._extract_persistence(connected)
        
        # Extract transactions
        packet.transactions = self._extract_transactions(connected)
        
        # Extract queries
        packet.queries = self._extract_queries(connected)
        
        # Extract external calls
        packet.external_calls = self._extract_external_calls(connected)
        
        # Extract tests
        packet.tests = self._extract_tests(connected)
        
        # Extract unresolved items
        packet.unresolved = self._extract_unresolved(connected)
        
        return packet
    
    def _build_summary(self, connected: ConnectedGraph) -> str:
        """Build a human-readable summary of the changes.
        
        Args:
            connected: The connected graph
            
        Returns:
            Summary string
        """
        parts = []
        
        # Count groups by type
        type_counts: Dict[str, int] = {}
        for group in connected.groups.values():
            type_counts[group.type] = type_counts.get(group.type, 0) + 1
        
        # Build summary
        if type_counts:
            parts.append(f"Changed {len(connected.groups)} semantic units:")
            for group_type, count in sorted(type_counts.items()):
                parts.append(f"  - {count} {group_type}(s)")
        
        if connected.group_edges:
            parts.append(f"\n{len(connected.group_edges)} relationships between groups")
        
        return "\n".join(parts)
    
    def _extract_changed_areas(self, connected: ConnectedGraph) -> List[str]:
        """Extract changed areas from the graph.
        
        Args:
            connected: The connected graph
            
        Returns:
            List of changed area descriptions
        """
        areas = []
        
        for group in connected.groups.values():
            # Use group title as the changed area
            areas.append(group.title)
        
        return areas
    
    def _extract_semantic_changes(self, connected: ConnectedGraph) -> List[str]:
        """Extract semantic changes from the graph.
        
        Args:
            connected: The connected graph
            
        Returns:
            List of semantic change descriptions
        """
        changes = []
        
        for group in connected.groups.values():
            # Describe what changed in this group
            if group.type == "endpoint":
                changes.append(f"API endpoint modified: {group.title}")
            elif group.type == "model":
                changes.append(f"Data model modified: {group.title}")
            elif group.type == "migration":
                changes.append(f"Database migration: {group.title}")
            elif group.type == "validation":
                changes.append(f"Validation logic modified: {group.title}")
            elif group.type == "transaction":
                changes.append(f"Transaction boundary changed: {group.title}")
            elif group.type == "query":
                changes.append(f"Query semantics changed: {group.title}")
            elif group.type == "external_service":
                changes.append(f"External service integration: {group.title}")
            elif group.type == "test":
                changes.append(f"Test modified: {group.title}")
            else:
                changes.append(f"Service logic modified: {group.title}")
        
        return changes
    
    def _extract_relationships(self, connected: ConnectedGraph) -> List[Dict[str, Any]]:
        """Extract relationships between groups.
        
        Args:
            connected: The connected graph
            
        Returns:
            List of relationship dictionaries
        """
        relationships = []
        
        for edge in connected.group_edges:
            source_group = connected.groups.get(edge.source_group_id)
            target_group = connected.groups.get(edge.target_group_id)
            
            if source_group and target_group:
                relationships.append({
                    "from": source_group.title,
                    "to": target_group.title,
                    "type": edge.edge_type,
                })
        
        return relationships
    
    def _extract_migrations(self, connected: ConnectedGraph) -> List[str]:
        """Extract migrations from the graph.
        
        Args:
            connected: The connected graph
            
        Returns:
            List of migration descriptions
        """
        migrations = []
        
        for group in connected.groups.values():
            if group.type == "migration":
                # Extract migration details from nodes
                for node in group.nodes:
                    if node.node_type == NodeType.MIGRATION:
                        operations = node.properties.get('operations', [])
                        for op in operations:
                            if isinstance(op, dict):
                                op_type = op.get('type', '')
                                table = op.get('table', '')
                                column = op.get('column', '')
                                
                                if op_type and table:
                                    desc = f"{op_type} on {table}"
                                    if column:
                                        desc += f".{column}"
                                    migrations.append(desc)
        
        return migrations
    
    def _extract_validations(self, connected: ConnectedGraph) -> List[str]:
        """Extract validations from the graph.
        
        Args:
            connected: The connected graph
            
        Returns:
            List of validation descriptions
        """
        validations = []
        
        for group in connected.groups.values():
            if group.type == "validation":
                validations.append(group.title)
            else:
                # Check if group has validation-related nodes
                for node in group.nodes:
                    if node.node_type == NodeType.FUNCTION:
                        name_lower = node.name.lower()
                        if any(keyword in name_lower for keyword in ['validate', 'validation', 'check', 'verify']):
                            validations.append(f"Validation in {group.title}: {node.name}")
        
        return validations
    
    def _extract_persistence(self, connected: ConnectedGraph) -> List[str]:
        """Extract persistence changes from the graph.
        
        Args:
            connected: The connected graph
            
        Returns:
            List of persistence descriptions
        """
        persistence = []
        
        for group in connected.groups.values():
            if group.type == "model":
                persistence.append(f"Model modified: {group.title}")
                
                # Check for field changes
                for node in group.nodes:
                    if node.node_type == NodeType.FIELD and node.change_type != "unmodified":
                        persistence.append(f"  Field changed: {node.name}")
            elif group.type == "service":
                # Check for repository/persistence functions
                for node in group.nodes:
                    if node.node_type == NodeType.FUNCTION:
                        name_lower = node.name.lower()
                        if any(keyword in name_lower for keyword in ['save', 'create', 'update', 'delete', 'repository']):
                            persistence.append(f"Persistence operation: {group.title}.{node.name}")
        
        return persistence
    
    def _extract_transactions(self, connected: ConnectedGraph) -> List[str]:
        """Extract transactions from the graph.
        
        Args:
            connected: The connected graph
            
        Returns:
            List of transaction descriptions
        """
        transactions = []
        
        for group in connected.groups.values():
            if group.type == "transaction":
                transactions.append(f"Transaction boundary: {group.title}")
        
        return transactions
    
    def _extract_queries(self, connected: ConnectedGraph) -> List[str]:
        """Extract queries from the graph.
        
        Args:
            connected: The connected graph
            
        Returns:
            List of query descriptions
        """
        queries = []
        
        for group in connected.groups.values():
            if group.type == "query":
                queries.append(f"Query modified: {group.title}")
            else:
                # Check for query nodes in other groups
                for node in group.nodes:
                    if node.node_type == NodeType.QUERY:
                        queries.append(f"Query in {group.title}: {node.name}")
        
        return queries
    
    def _extract_external_calls(self, connected: ConnectedGraph) -> List[str]:
        """Extract external calls from the graph.
        
        Args:
            connected: The connected graph
            
        Returns:
            List of external call descriptions
        """
        external_calls = []
        
        for group in connected.groups.values():
            if group.type == "external_service":
                external_calls.append(f"External service: {group.title}")
            else:
                # Check for external service nodes in other groups
                for node in group.nodes:
                    if node.node_type == NodeType.EXTERNAL_SERVICE:
                        service_type = node.properties.get('service_type', node.name)
                        external_calls.append(f"External call in {group.title}: {service_type}")
        
        return external_calls
    
    def _extract_tests(self, connected: ConnectedGraph) -> List[Dict[str, Any]]:
        """Extract tests from the graph.
        
        Args:
            connected: The connected graph
            
        Returns:
            List of test dictionaries
        """
        tests = []
        
        for group in connected.groups.values():
            if group.type == "test":
                test_info = {
                    "name": group.title,
                    "group_id": group.id,
                }
                
                # Check if test is modified or added
                for node in group.nodes:
                    if node.node_type == NodeType.TEST:
                        test_info["change_type"] = node.change_type
                        test_info["target_functions"] = node.properties.get('target_functions', [])
                        break
                
                tests.append(test_info)
        
        return tests
    
    def _extract_unresolved(self, connected: ConnectedGraph) -> List[str]:
        """Extract unresolved items from the graph.
        
        Args:
            connected: The connected graph
            
        Returns:
            List of unresolved item descriptions
        """
        unresolved = []
        
        # Check for ungrouped nodes
        # Note: ConnectedGraph doesn't have ungrouped_nodes, so we skip this
        
        # Check for isolated groups (no relationships)
        groups_with_relationships = set()
        for edge in connected.group_edges:
            groups_with_relationships.add(edge.source_group_id)
            groups_with_relationships.add(edge.target_group_id)
        
        for group_id, group in connected.groups.items():
            if group_id not in groups_with_relationships:
                unresolved.append(f"No relationships defined for: {group.title}")
        
        return unresolved
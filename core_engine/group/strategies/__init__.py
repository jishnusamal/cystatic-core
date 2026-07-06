"""Grouping strategies for collapsing nodes into semantic units."""

from __future__ import annotations

from typing import List, Optional

from language_adapters.ir.nodes import BaseNode, NodeType
from core_engine.group import GroupStrategy
from core_engine.graph import FilteredGraph


class ByServiceStrategy:
    """Group nodes by service/module."""
    
    def assign_group(self, node: BaseNode, graph: FilteredGraph) -> Optional[str]:
        """Assign node to a service group based on file path.
        
        Args:
            node: The node to group
            graph: The filtered graph for context
            
        Returns:
            Service group ID or None
        """
        # Extract service name from file path
        # e.g., "services/user_service.py" -> "user_service"
        # e.g., "api/users.py" -> "api_users"
        file_path = node.file_path
        
        # Split path and get meaningful parts
        parts = file_path.replace('\\', '/').split('/')
        
        # Look for common service indicators
        service_indicators = ['services', 'service', 'api', 'handlers', 'views']
        
        for i, part in enumerate(parts):
            if part.lower() in service_indicators and i + 1 < len(parts):
                # Get the next part (the actual service name)
                service_name = parts[i + 1].replace('.py', '')
                return f"service:{service_name}"
        
        # Fallback: use the filename
        filename = parts[-1].replace('.py', '')
        if filename:
            return f"service:{filename}"
        
        return None


class ByModelStrategy:
    """Group nodes by ORM model."""
    
    def assign_group(self, node: BaseNode, graph: FilteredGraph) -> Optional[str]:
        """Assign node to a model group.
        
        Args:
            node: The node to group
            graph: The filtered graph for context
            
        Returns:
            Model group ID or None
        """
        if node.node_type == NodeType.MODEL:
            return f"model:{node.name}"
        
        if node.node_type == NodeType.FIELD:
            model_name = node.properties.get('model_name', '')
            if model_name:
                return f"model:{model_name}"
        
        if node.node_type == NodeType.FUNCTION:
            # Check if function name suggests it's related to a model
            name_lower = node.name.lower()
            for model_node in graph.nodes.values():
                if model_node.node_type == NodeType.MODEL:
                    model_name = model_node.name
                    if model_name.lower() in name_lower:
                        return f"model:{model_name}"
        
        return None


class ByEndpointStrategy:
    """Group nodes by API endpoint."""
    
    def assign_group(self, node: BaseNode, graph: FilteredGraph) -> Optional[str]:
        """Assign node to an endpoint group.
        
        Args:
            node: The node to group
            graph: The filtered graph for context
            
        Returns:
            Endpoint group ID or None
        """
        if node.node_type == NodeType.ENDPOINT:
            route = node.properties.get('route', node.name)
            method = node.properties.get('method', '')
            if method:
                return f"endpoint:{method}:{route}"
            return f"endpoint:{route}"
        
        return None


class ByMigrationStrategy:
    """Group nodes by migration."""
    
    def assign_group(self, node: BaseNode, graph: FilteredGraph) -> Optional[str]:
        """Assign node to a migration group.
        
        Args:
            node: The node to group
            graph: The filtered graph for context
            
        Returns:
            Migration group ID or None
        """
        if node.node_type == NodeType.MIGRATION:
            return f"migration:{node.name}"
        
        if node.node_type in (NodeType.TABLE, NodeType.COLUMN):
            # Check if this table/column is created/modified by a migration
            for migration_node in graph.nodes.values():
                if migration_node.node_type == NodeType.MIGRATION:
                    operations = migration_node.properties.get('operations', [])
                    for op in operations:
                        if isinstance(op, dict):
                            table_name = op.get('table', '')
                            if table_name and (node.name == table_name or 
                                             node.properties.get('table_name') == table_name):
                                return f"migration:{migration_node.name}"
        
        return None


class ByTestStrategy:
    """Group nodes by test suite."""
    
    def assign_group(self, node: BaseNode, graph: FilteredGraph) -> Optional[str]:
        """Assign node to a test group.
        
        Args:
            node: The node to group
            graph: The filtered graph for context
            
        Returns:
            Test group ID or None
        """
        if node.node_type == NodeType.TEST:
            # Extract test file/module name
            file_path = node.file_path
            parts = file_path.replace('\\', '/').split('/')
            
            # Look for tests directory
            for i, part in enumerate(parts):
                if part.lower() in ['tests', 'test'] and i + 1 < len(parts):
                    test_module = parts[i + 1].replace('.py', '')
                    return f"test:{test_module}"
            
            # Fallback to filename
            filename = parts[-1].replace('.py', '')
            if filename:
                return f"test:{filename}"
        
        return None


class ByTransactionStrategy:
    """Group nodes by transaction."""
    
    def assign_group(self, node: BaseNode, graph: FilteredGraph) -> Optional[str]:
        """Assign node to a transaction group.
        
        Args:
            node: The node to group
            graph: The filtered graph for context
            
        Returns:
            Transaction group ID or None
        """
        if node.node_type == NodeType.TRANSACTION:
            return f"transaction:{node.name}"
        
        if node.node_type == NodeType.FUNCTION:
            name_lower = node.name.lower()
            if 'transaction' in name_lower or 'atomic' in name_lower:
                return f"transaction:{node.name}"
        
        return None


class ByExternalAPIStrategy:
    """Group nodes by external API/service."""
    
    def assign_group(self, node: BaseNode, graph: FilteredGraph) -> Optional[str]:
        """Assign node to an external API group.
        
        Args:
            node: The node to group
            graph: The filtered graph for context
            
        Returns:
            External API group ID or None
        """
        if node.node_type == NodeType.EXTERNAL_SERVICE:
            service_type = node.properties.get('service_type', node.name)
            return f"external:{service_type}"
        
        return None
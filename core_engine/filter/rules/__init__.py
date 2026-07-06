"""Filter rules for removing low-value graph information."""

from __future__ import annotations

from typing import List

from language_adapters.ir.nodes import BaseNode, NodeType
from language_adapters.ir.edges import BaseEdge

from core_engine.filter import FilterRule


class IgnoreImportsRule:
    """Remove import statements."""
    
    def keep_node(self, node: BaseNode, graph) -> bool:
        """Keep node if it's not an import."""
        # Imports are typically not represented as nodes, but if they are, filter them
        return True
    
    def keep_edge(self, edge: BaseEdge, graph) -> bool:
        """Keep all edges."""
        return True


class IgnoreDecoratorRule:
    """Remove decorator nodes that don't add semantic value."""
    
    def keep_node(self, node: BaseNode, graph) -> bool:
        """Keep decorators only if they're significant (e.g., auth, validation)."""
        if node.node_type == NodeType.DECORATOR:
            # Keep significant decorators
            significant_decorators = {
                'login_required', 'authenticated', 'permission_required',
                'validate', 'validator', 'transaction', 'atomic',
            }
            decorator_name = node.name.lower()
            return any(sig in decorator_name for sig in significant_decorators)
        return True
    
    def keep_edge(self, edge: BaseEdge, graph) -> bool:
        """Keep all edges."""
        return True


class IgnoreDocstringRule:
    """Remove docstring nodes."""
    
    def keep_node(self, node: BaseNode, graph) -> bool:
        """Keep node if it's not a docstring."""
        # Docstrings are typically not separate nodes, but filter if they are
        return True
    
    def keep_edge(self, edge: BaseEdge, graph) -> bool:
        """Keep all edges."""
        return True


class IgnoreTypeHintRule:
    """Remove type hint-only changes."""
    
    def keep_node(self, node: BaseNode, graph) -> bool:
        """Keep all nodes - type hints are part of function/method nodes."""
        return True
    
    def keep_edge(self, edge: BaseEdge, graph) -> bool:
        """Keep all edges."""
        return True


class KeepChangedAPIBoundaryRule:
    """Keep nodes at API boundaries that have changed."""
    
    def keep_node(self, node: BaseNode, graph) -> bool:
        """Keep endpoints and exposed functions."""
        if node.node_type == NodeType.ENDPOINT:
            return True
        if node.node_type == NodeType.FUNCTION and node.change_type != "unmodified":
            return True
        if node.node_type == NodeType.METHOD and node.change_type != "unmodified":
            return True
        return True  # Let other rules decide
    
    def keep_edge(self, edge: BaseEdge, graph) -> bool:
        """Keep all edges."""
        return True


class KeepValidationRule:
    """Keep validation-related nodes."""
    
    def keep_node(self, node: BaseNode, graph) -> bool:
        """Keep validation nodes."""
        if node.node_type == NodeType.FUNCTION:
            name_lower = node.name.lower()
            if any(keyword in name_lower for keyword in ['validate', 'validation', 'check', 'verify']):
                return True
        if node.node_type == NodeType.FIELD and node.change_type != "unmodified":
            return True
        return True  # Let other rules decide
    
    def keep_edge(self, edge: BaseEdge, graph) -> bool:
        """Keep validation edges."""
        if edge.edge_type.name == "VALIDATES":
            return True
        return True  # Let other rules decide


class KeepPersistenceRule:
    """Keep persistence-related nodes."""
    
    def keep_node(self, node: BaseNode, graph) -> bool:
        """Keep persistence nodes."""
        if node.node_type in (NodeType.MODEL, NodeType.FIELD, NodeType.MIGRATION):
            return True
        if node.node_type == NodeType.FUNCTION:
            name_lower = node.name.lower()
            if any(keyword in name_lower for keyword in ['save', 'create', 'update', 'delete', 'repository', 'repo']):
                return True
        return True  # Let other rules decide
    
    def keep_edge(self, edge: BaseEdge, graph) -> bool:
        """Keep persistence edges."""
        if edge.edge_type.name in ("WRITES", "READS", "CREATES", "UPDATES", "DELETES"):
            return True
        return True  # Let other rules decide


class KeepTransactionRule:
    """Keep transaction-related nodes."""
    
    def keep_node(self, node: BaseNode, graph) -> bool:
        """Keep transaction nodes."""
        if node.node_type == NodeType.TRANSACTION:
            return True
        if node.node_type == NodeType.FUNCTION:
            name_lower = node.name.lower()
            if 'transaction' in name_lower or 'atomic' in name_lower:
                return True
        return True  # Let other rules decide
    
    def keep_edge(self, edge: BaseEdge, graph) -> bool:
        """Keep all edges."""
        return True


class KeepMigrationRule:
    """Keep migration-related nodes."""
    
    def keep_node(self, node: BaseNode, graph) -> bool:
        """Keep migration nodes."""
        if node.node_type == NodeType.MIGRATION:
            return True
        if node.node_type in (NodeType.TABLE, NodeType.COLUMN):
            return True
        return True  # Let other rules decide
    
    def keep_edge(self, edge: BaseEdge, graph) -> bool:
        """Keep migration edges."""
        if edge.edge_type.name == "MIGRATES":
            return True
        return True  # Let other rules decide


class IgnoreLocalVariableRule:
    """Remove local variable nodes."""
    
    def keep_node(self, node: BaseNode, graph) -> bool:
        """Keep node if it's not a local variable."""
        # Local variables are typically not represented as separate nodes
        # but if they are, filter them out
        return True
    
    def keep_edge(self, edge: BaseEdge, graph) -> bool:
        """Keep all edges."""
        return True


class IgnoreParameterRule:
    """Remove parameter-only changes."""
    
    def keep_node(self, node: BaseNode, graph) -> bool:
        """Keep all nodes - parameters are part of function/method nodes."""
        return True
    
    def keep_edge(self, edge: BaseEdge, graph) -> bool:
        """Keep all edges."""
        return True


class IgnoreTestHelperRule:
    """Remove test helper/utility functions."""
    
    def keep_node(self, node: BaseNode, graph) -> bool:
        """Keep test nodes unless they're helpers."""
        if node.node_type == NodeType.TEST:
            # Keep all test nodes - we can't easily distinguish helpers
            return True
        return True
    
    def keep_edge(self, edge: BaseEdge, graph) -> bool:
        """Keep all edges."""
        return True

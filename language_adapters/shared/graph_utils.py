"""Graph traversal and analysis utilities."""

from __future__ import annotations

from typing import Dict, List, Optional, Set, Tuple

from language_adapters.ir import (
    SemanticGraph,
    BaseNode,
    BaseEdge,
    NodeType,
    EdgeType,
)


class GraphUtils:
    """Utility methods for graph traversal and analysis."""

    @staticmethod
    def find_reachable_nodes(
        graph: SemanticGraph,
        start: BaseNode,
        edge_types: Optional[Set[EdgeType]] = None,
        max_depth: int = 10,
    ) -> Set[BaseNode]:
        """Find all nodes reachable from start via specified edge types."""
        visited: Set[BaseNode] = set()
        stack: List[Tuple[BaseNode, int]] = [(start, 0)]

        while stack:
            current, depth = stack.pop()
            if depth > max_depth or current in visited:
                continue
            visited.add(current)

            for edge in graph.get_edges_from(current):
                if edge_types is None or edge.edge_type in edge_types:
                    stack.append((edge.target, depth + 1))

        return visited

    @staticmethod
    def find_upstream_dependencies(
        graph: SemanticGraph,
        node: BaseNode,
        max_depth: int = 5,
    ) -> Set[BaseNode]:
        """Find all nodes that depend on (call/read/use) the given node."""
        visited: Set[BaseNode] = set()
        stack: List[Tuple[BaseNode, int]] = [(node, 0)]

        while stack:
            current, depth = stack.pop()
            if depth > max_depth or current in visited:
                continue
            visited.add(current)

            for edge in graph.get_edges_to(current):
                stack.append((edge.source, depth + 1))

        return visited

    @staticmethod
    def find_downstream_dependencies(
        graph: SemanticGraph,
        node: BaseNode,
        max_depth: int = 5,
    ) -> Set[BaseNode]:
        """Find all nodes that the given node depends on."""
        visited: Set[BaseNode] = set()
        stack: List[Tuple[BaseNode, int]] = [(node, 0)]

        while stack:
            current, depth = stack.pop()
            if depth > max_depth or current in visited:
                continue
            visited.add(current)

            for edge in graph.get_edges_from(current):
                stack.append((edge.target, depth + 1))

        return visited

    @staticmethod
    def get_subgraph(
        graph: SemanticGraph,
        nodes: Set[BaseNode],
    ) -> SemanticGraph:
        """Extract a subgraph containing only the given nodes and their edges."""
        subgraph = SemanticGraph()
        node_set = set(nodes)

        for node in node_set:
            subgraph.add_node(node)

        for edge in graph.edges:
            if edge.source in node_set and edge.target in node_set:
                subgraph.add_edge(edge)

        return subgraph

    @staticmethod
    def get_changed_nodes(graph: SemanticGraph) -> List[BaseNode]:
        """Get all nodes that were added, modified, or deleted."""
        return [
            n for n in graph.nodes.values()
            if n.change_type in ("added", "modified", "deleted", "renamed")
        ]

    @staticmethod
    def get_changed_edges(graph: SemanticGraph) -> List[BaseEdge]:
        """Get all edges that were added or removed."""
        return [
            e for e in graph.edges
            if e.change_type in ("added", "removed")
        ]

    @staticmethod
    def find_impacted_nodes(
        graph: SemanticGraph,
        changed_nodes: List[BaseNode],
        max_depth: int = 3,
    ) -> Set[BaseNode]:
        """Find all nodes potentially impacted by the changed nodes."""
        impacted: Set[BaseNode] = set()
        for node in changed_nodes:
            impacted.update(
                GraphUtils.find_upstream_dependencies(graph, node, max_depth)
            )
            impacted.update(
                GraphUtils.find_downstream_dependencies(graph, node, max_depth)
            )
        return impacted
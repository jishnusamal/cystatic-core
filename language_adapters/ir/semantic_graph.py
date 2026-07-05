"""Semantic graph — the single output of every language adapter."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from language_adapters.ir.nodes import BaseNode, NodeType
from language_adapters.ir.edges import BaseEdge, EdgeType


@dataclass
class SemanticGraph:
    """Language-agnostic semantic graph.

    This is the single output of every language adapter.
    The core engine consumes this graph to derive signals.
    """

    nodes: Dict[str, BaseNode] = field(default_factory=dict)
    edges: List[BaseEdge] = field(default_factory=list)
    file_paths: Set[str] = field(default_factory=set)

    # ------------------------------------------------------------------
    # Node operations
    # ------------------------------------------------------------------

    def add_node(self, node: BaseNode) -> BaseNode:
        """Add a node to the graph. Returns the node (existing or new)."""
        key = self._node_key(node)
        if key not in self.nodes:
            self.nodes[key] = node
            self.file_paths.add(node.file_path)
        return self.nodes[key]

    def get_node(self, node_type: NodeType, name: str, file_path: str, class_name: str = "") -> Optional[BaseNode]:
        """Look up a node by type, name, and file path."""
        if node_type == NodeType.METHOD and class_name:
            key = f"{node_type.name}:{name}:{class_name}:{file_path}"
        else:
            key = f"{node_type.name}:{name}:{file_path}"
        return self.nodes.get(key)

    def get_nodes_by_type(self, node_type: NodeType) -> List[BaseNode]:
        """Get all nodes of a given type."""
        return [n for n in self.nodes.values() if n.node_type == node_type]

    def get_nodes_by_file(self, file_path: str) -> List[BaseNode]:
        """Get all nodes in a given file."""
        return [n for n in self.nodes.values() if n.file_path == file_path]

    def has_node(self, node: BaseNode) -> bool:
        """Check if a node exists in the graph."""
        return self._node_key(node) in self.nodes

    def remove_node(self, node: BaseNode) -> bool:
        """Remove a node and all its edges. Returns True if removed."""
        key = self._node_key(node)
        if key not in self.nodes:
            return False
        del self.nodes[key]
        self.edges = [
            e
            for e in self.edges
            if e.source != node and e.target != node
        ]
        return True

    # ------------------------------------------------------------------
    # Edge operations
    # ------------------------------------------------------------------

    def add_edge(self, edge: BaseEdge) -> BaseEdge:
        """Add an edge to the graph. Deduplicates automatically."""
        # Ensure both endpoints are in the graph
        self.add_node(edge.source)
        self.add_node(edge.target)

        if edge not in self.edges:
            self.edges.append(edge)
        return edge

    def get_edges(self, edge_type: Optional[EdgeType] = None) -> List[BaseEdge]:
        """Get all edges, optionally filtered by type."""
        if edge_type is None:
            return list(self.edges)
        return [e for e in self.edges if e.edge_type == edge_type]

    def get_edges_from(self, node: BaseNode) -> List[BaseEdge]:
        """Get all edges originating from a node."""
        return [e for e in self.edges if e.source == node]

    def get_edges_to(self, node: BaseNode) -> List[BaseEdge]:
        """Get all edges targeting a node."""
        return [e for e in self.edges if e.target == node]

    def has_edge(self, edge: BaseEdge) -> bool:
        """Check if an edge exists in the graph."""
        return edge in self.edges

    def remove_edge(self, edge: BaseEdge) -> bool:
        """Remove an edge. Returns True if removed."""
        if edge not in self.edges:
            return False
        self.edges.remove(edge)
        return True

    # ------------------------------------------------------------------
    # Merge / deduplicate
    # ------------------------------------------------------------------

    def merge(self, other: SemanticGraph) -> SemanticGraph:
        """Merge another graph into this one."""
        for node in other.nodes.values():
            self.add_node(node)
        for edge in other.edges:
            self.add_edge(edge)
        return self

    def deduplicate(self) -> SemanticGraph:
        """Remove duplicate edges."""
        unique: List[BaseEdge] = []
        seen: List[BaseEdge] = []
        for edge in self.edges:
            # Use linear search since edges may not be hashable during initialization
            if not any(edge == s for s in seen):
                seen.append(edge)
                unique.append(edge)
        self.edges = unique
        return self

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def find_path(
        self,
        source: BaseNode,
        target: BaseNode,
        max_depth: int = 10,
    ) -> List[List[BaseEdge]]:
        """Find all paths between source and target (BFS)."""
        paths: List[List[BaseEdge]] = []
        self._bfs(source, target, [], set(), paths, max_depth)
        return paths

    def _bfs(
        self,
        current: BaseNode,
        target: BaseNode,
        path: List[BaseEdge],
        visited: Set[str],
        paths: List[List[BaseEdge]],
        max_depth: int,
    ) -> None:
        if len(path) > max_depth:
            return
        if current == target:
            paths.append(list(path))
            return

        key = self._node_key(current)
        if key in visited:
            return
        visited.add(key)

        for edge in self.get_edges_from(current):
            path.append(edge)
            self._bfs(edge.target, target, path, visited, paths, max_depth)
            path.pop()

        visited.discard(key)

    def to_dict(self) -> dict:
        """Serialize graph to a plain dict (for debugging / serialization)."""
        return {
            "nodes": [
                {
                    "type": n.node_type.name,
                    "name": n.name,
                    "file_path": n.file_path,
                    "change_type": n.change_type,
                    "properties": n.properties,
                }
                for n in self.nodes.values()
            ],
            "edges": [
                {
                    "type": e.edge_type.name,
                    "source": self._node_key(e.source),
                    "target": self._node_key(e.target),
                    "change_type": e.change_type,
                    "properties": e.properties,
                }
                for e in self.edges
            ],
            "file_paths": sorted(self.file_paths),
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _node_key(node: BaseNode) -> str:
        # Include class_name for methods to distinguish Base.save from Child.save
        if hasattr(node, 'class_name') and node.node_type == NodeType.METHOD:
            return f"{node.node_type.name}:{node.name}:{node.class_name}:{node.file_path}"
        return f"{node.node_type.name}:{node.name}:{node.file_path}"

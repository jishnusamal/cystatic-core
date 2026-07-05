"""Graph traverser — provides graph traversal utilities for analyzers."""

from __future__ import annotations

from collections import deque
from typing import Callable, Dict, List, Optional, Set, Tuple

from language_adapters.ir.nodes import BaseNode, NodeType
from language_adapters.ir.edges import BaseEdge, EdgeType

from core_engine.models.semantic_graph import ValidatedSemanticGraph


class GraphTraverser:
    """Utility for traversing the validated semantic graph.

    Provides BFS, DFS, reachability, and path-finding operations
    used by all analyzers.
    """

    def __init__(self, graph: ValidatedSemanticGraph):
        self.graph = graph

    def bfs(
        self,
        start: BaseNode,
        max_depth: int = 10,
        edge_filter: Callable[[BaseEdge], bool] | None = None,
        node_filter: Callable[[BaseNode], bool] | None = None,
    ) -> List[Tuple[BaseNode, int]]:
        """BFS traversal from a start node.

        Returns list of (node, depth) tuples.
        """
        visited: Set[str] = set()
        queue: deque[Tuple[BaseNode, int]] = deque()
        result: List[Tuple[BaseNode, int]] = []

        queue.append((start, 0))
        visited.add(self._key(start))

        while queue:
            node, depth = queue.popleft()
            result.append((node, depth))

            if depth >= max_depth:
                continue

            for edge in self.graph.get_edges_from(node):
                if edge_filter and not edge_filter(edge):
                    continue
                target = edge.target
                if target is None:
                    continue
                target_key = self._key(target)
                if target_key not in visited:
                    visited.add(target_key)
                    if node_filter is None or node_filter(target):
                        queue.append((target, depth + 1))

        return result

    def dfs(
        self,
        start: BaseNode,
        max_depth: int = 10,
        edge_filter: Callable[[BaseEdge], bool] | None = None,
    ) -> List[List[BaseNode]]:
        """DFS traversal to find all paths from start to sinks."""
        paths: List[List[BaseNode]] = []
        self._dfs_recursive(start, [start], set(), paths, max_depth, edge_filter)
        return paths

    def _dfs_recursive(
        self,
        current: BaseNode,
        path: List[BaseNode],
        visited: Set[str],
        paths: List[List[BaseNode]],
        max_depth: int,
        edge_filter: Callable[[BaseEdge], bool] | None,
    ) -> None:
        if len(path) > max_depth:
            return

        outgoing = self.graph.get_edges_from(current)

        # If no outgoing edges (or none matching filter), this is a sink — record path
        matching = [e for e in outgoing if edge_filter is None or edge_filter(e)]
        if not matching:
            paths.append(list(path))
            return

        for edge in matching:
            target = edge.target
            if target is None:
                continue
            target_key = self._key(target)
            if target_key in visited:
                continue
            visited.add(target_key)
            path.append(target)
            self._dfs_recursive(target, path, visited, paths, max_depth, edge_filter)
            path.pop()
            visited.discard(target_key)

    def find_paths_between(
        self,
        source: BaseNode,
        target: BaseNode,
        max_depth: int = 10,
    ) -> List[List[BaseEdge]]:
        """Find all edge paths between two nodes."""
        return self.graph.graph.find_path(source, target, max_depth)

    def get_reachable_nodes(
        self,
        start: BaseNode,
        max_depth: int = 10,
        edge_filter: Callable[[BaseEdge], bool] | None = None,
    ) -> Set[str]:
        """Get all node keys reachable from start."""
        visited: Set[str] = set()
        queue: deque[Tuple[BaseNode, int]] = deque()
        queue.append((start, 0))
        visited.add(self._key(start))

        while queue:
            node, depth = queue.popleft()
            if depth >= max_depth:
                continue

            for edge in self.graph.get_edges_from(node):
                if edge_filter and not edge_filter(edge):
                    continue
                target = edge.target
                if target is None:
                    continue
                target_key = self._key(target)
                if target_key not in visited:
                    visited.add(target_key)
                    queue.append((target, depth + 1))

        return visited

    def get_affected_nodes(
        self,
        changed_nodes: List[BaseNode],
        max_depth: int = 3,
    ) -> List[BaseNode]:
        """Get all nodes affected by (reachable from) changed nodes."""
        affected: Set[str] = set()
        for node in changed_nodes:
            affected.update(
                self.get_reachable_nodes(node, max_depth=max_depth)
            )
        return [
            n for n in self.graph.graph.nodes.values()
            if self._key(n) in affected
        ]

    @staticmethod
    def _key(node: BaseNode) -> str:
        return f"{node.node_type.name}:{node.name}:{node.file_path}"
"""Execution path analyzer — finds execution paths through changed code."""

from __future__ import annotations

from typing import Dict, List, Set
from collections import deque

from language_adapters.ir.nodes import BaseNode, NodeType
from language_adapters.ir.edges import BaseEdge, EdgeType

from core_engine.models.semantic_graph import ValidatedSemanticGraph
from core_engine.models.evidence import ExecutionPath, ExecutionEvidence, Signal
from core_engine.analyzers.graph_traverser import GraphTraverser


class ExecutionPathAnalyzer:
    """Analyzes execution paths through the changed code.

    Finds:
    - Entrypoints (APIs, event handlers, etc.)
    - Sinks (database writes, external calls, etc.)
    - Full paths from entrypoints to sinks
    - Affected reads, writes, and services along each path
    """

    def __init__(self, graph: ValidatedSemanticGraph):
        self.graph = graph
        self.traverser = GraphTraverser(graph)

    def analyze(self) -> ExecutionEvidence:
        """Analyze execution paths and return evidence."""
        paths: List[ExecutionPath] = []
        entrypoints = self._find_entrypoints()
        sinks = self._find_sinks()

        path_counter: Dict[str, int] = {}

        for entrypoint in entrypoints:
            for sink in sinks:
                found_paths = self.traverser.find_paths_between(entrypoint, sink, max_depth=15)
                for edge_path in found_paths:
                    path_nodes = self._edge_path_to_nodes(edge_path)
                    if not path_nodes:
                        continue

                    path_id = self._make_path_id(entrypoint, sink)
                    path_counter[path_id] = path_counter.get(path_id, 0) + 1

                    # Only add unique paths (deduplicate by node sequence)
                    path_key = "->".join(self._key(n) for n in path_nodes)
                    if path_counter.get(path_key, 0) > 1:
                        continue
                    path_counter[path_key] = 1

                    affected_reads = self._find_affected_reads(path_nodes)
                    affected_writes = self._find_affected_writes(path_nodes)
                    affected_services = self._find_affected_services(path_nodes)

                    paths.append(
                        ExecutionPath(
                            path_id=path_id,
                            entrypoint=self._key(entrypoint),
                            sink=self._key(sink),
                            nodes=[self._key(n) for n in path_nodes],
                            edges=[str(e) for e in edge_path],
                            affected_reads=list(affected_reads),
                            affected_writes=list(affected_writes),
                            affected_services=list(affected_services),
                            count=1,
                        )
                    )

        # Deduplicate paths with same entrypoint/sink
        deduplicated = self._deduplicate_paths(paths)

        return ExecutionEvidence(
            description=f"Found {len(deduplicated)} unique execution paths through changed code",
            paths=deduplicated,
            confidence=0.95,
        )

    def _find_entrypoints(self) -> List[BaseNode]:
        """Find entrypoints: endpoints, event subscribers, queue consumers."""
        entrypoints: List[BaseNode] = []

        # Endpoints are always entrypoints
        entrypoints.extend(self.graph.get_nodes_by_type(NodeType.ENDPOINT))

        # Event subscribers
        for edge in self.graph.graph.get_edges(EdgeType.SUBSCRIBES):
            if edge.source and edge.source not in entrypoints:
                entrypoints.append(edge.source)

        # Functions with no callers (orphan functions that might be entrypoints)
        for node in self.graph.get_nodes_by_type(NodeType.FUNCTION):
            if node not in entrypoints and not self.graph.get_edges_to(node):
                entrypoints.append(node)

        return entrypoints

    def _find_sinks(self) -> List[BaseNode]:
        """Find sinks: database writes, external calls, event publishes."""
        sinks: List[BaseNode] = []

        # Database writes
        for edge in self.graph.graph.get_edges(EdgeType.WRITES):
            if edge.target and edge.target not in sinks:
                sinks.append(edge.target)

        # External services
        sinks.extend(self.graph.get_nodes_by_type(NodeType.EXTERNAL_SERVICE))

        # Event publishes
        for edge in self.graph.graph.get_edges(EdgeType.PUBLISHES):
            if edge.target and edge.target not in sinks:
                sinks.append(edge.target)

        # Cache writes
        for node in self.graph.get_nodes_by_type(NodeType.CACHE):
            if getattr(node, "operation", "") == "set" and node not in sinks:
                sinks.append(node)

        return sinks

    def _edge_path_to_nodes(self, edge_path: List[BaseEdge]) -> List[BaseNode]:
        """Convert an edge path to an ordered list of unique nodes."""
        if not edge_path:
            return []
        nodes: List[BaseNode] = []
        seen: Set[str] = set()
        for edge in edge_path:
            if edge.source and self._key(edge.source) not in seen:
                nodes.append(edge.source)
                seen.add(self._key(edge.source))
            if edge.target and self._key(edge.target) not in seen:
                nodes.append(edge.target)
                seen.add(self._key(edge.target))
        return nodes

    def _find_affected_reads(self, path_nodes: List[BaseNode]) -> Set[str]:
        """Find database/models read along this path."""
        reads: Set[str] = set()
        for node in path_nodes:
            for edge in self.graph.get_edges_from(node):
                if edge.edge_type == EdgeType.READS and edge.target:
                    reads.add(self._key(edge.target))
        return reads

    def _find_affected_writes(self, path_nodes: List[BaseNode]) -> Set[str]:
        """Find database/models written along this path."""
        writes: Set[str] = set()
        for node in path_nodes:
            for edge in self.graph.get_edges_from(node):
                if edge.edge_type in (EdgeType.WRITES, EdgeType.CREATES, EdgeType.UPDATES, EdgeType.DELETES):
                    if edge.target:
                        writes.add(self._key(edge.target))
        return writes

    def _find_affected_services(self, path_nodes: List[BaseNode]) -> Set[str]:
        """Find external services called along this path."""
        services: Set[str] = set()
        for node in path_nodes:
            for edge in self.graph.get_edges_from(node):
                if edge.edge_type == EdgeType.SENDS_HTTP and edge.target:
                    services.add(self._key(edge.target))
        return services

    def _deduplicate_paths(self, paths: List[ExecutionPath]) -> List[ExecutionPath]:
        """Deduplicate paths with same entrypoint/sink by merging counts."""
        seen: Dict[str, ExecutionPath] = {}
        for path in paths:
            key = f"{path.entrypoint}->{path.sink}"
            if key in seen:
                seen[key].count += 1
            else:
                seen[key] = path
        return list(seen.values())

    @staticmethod
    def _key(node: BaseNode) -> str:
        return f"{node.node_type.name}:{node.name}:{node.file_path}"

    @staticmethod
    def _make_path_id(entrypoint: BaseNode, sink: BaseNode) -> str:
        return f"path:{entrypoint.name}->{sink.name}"
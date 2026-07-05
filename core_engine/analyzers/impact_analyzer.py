"""Impact analyzer — determines the blast radius of changes."""

from __future__ import annotations

from typing import Dict, List, Set

from language_adapters.ir.nodes import BaseNode, NodeType
from language_adapters.ir.edges import EdgeType

from core_engine.models.semantic_graph import ValidatedSemanticGraph
from core_engine.models.evidence import Evidence, EvidenceCategory, Signal
from core_engine.analyzers.graph_traverser import GraphTraverser


class ImpactAnalyzer:
    """Analyzes the impact/blast radius of changes.

    Determines:
    - Which services are affected
    - Which data is affected
    - Which endpoints are affected
    - The reach of each change through the call graph
    """

    def __init__(self, graph: ValidatedSemanticGraph):
        self.graph = graph
        self.traverser = GraphTraverser(graph)

    def analyze(self) -> Evidence:
        """Analyze impact of changes."""
        changed_nodes = self._get_changed_nodes()
        affected_nodes = self.traverser.get_affected_nodes(changed_nodes, max_depth=5)

        affected_services = self._get_affected_services(affected_nodes)
        affected_endpoints = self._get_affected_endpoints(affected_nodes)
        affected_data = self._get_affected_data(affected_nodes)
        affected_files = self._get_affected_files(affected_nodes)

        signals = [
            Signal(
                name="ImpactAnalysisComplete",
                rule_name="ImpactAnalyzer",
                description=f"Changes affect {len(affected_services)} services, "
                           f"{len(affected_endpoints)} endpoints, "
                           f"{len(affected_data)} data entities",
                node_ids=[self._key(n) for n in changed_nodes],
                properties={
                    "changed_count": len(changed_nodes),
                    "affected_count": len(affected_nodes),
                    "service_count": len(affected_services),
                    "endpoint_count": len(affected_endpoints),
                    "data_count": len(affected_data),
                },
            )
        ]

        return Evidence(
            category=EvidenceCategory.EXECUTION,
            description=f"Impact analysis: {len(changed_nodes)} changed nodes "
                       f"affect {len(affected_nodes)} total nodes across "
                       f"{len(affected_services)} services",
            signals=signals,
            confidence=0.90,
            node_ids=[self._key(n) for n in changed_nodes],
            properties={
                "affected_services": list(affected_services),
                "affected_endpoints": list(affected_endpoints),
                "affected_data": list(affected_data),
                "affected_files": list(affected_files),
            },
        )

    def _get_changed_nodes(self) -> List[BaseNode]:
        """Get all nodes that were added, modified, or deleted."""
        return [
            n for n in self.graph.graph.nodes.values()
            if n.change_type in ("added", "modified", "deleted")
        ]

    def _get_affected_services(self, nodes: List[BaseNode]) -> Set[str]:
        """Get unique service/domain names from affected nodes."""
        services: Set[str] = set()
        for node in nodes:
            parts = node.file_path.split("/")
            if parts:
                services.add(parts[0])
        return services

    def _get_affected_endpoints(self, nodes: List[BaseNode]) -> Set[str]:
        """Get endpoint routes affected by changes."""
        endpoints: Set[str] = set()
        for node in nodes:
            if node.node_type == NodeType.ENDPOINT:
                route = getattr(node, "route", None) or getattr(node, "method", "") + " " + getattr(node, "route", "")
                endpoints.add(route)
            # Also check if any endpoint calls this node
            for edge in self.graph.get_edges_to(node):
                if edge.source and edge.source.node_type == NodeType.ENDPOINT:
                    route = getattr(edge.source, "route", None) or getattr(edge.source, "name", "")
                    endpoints.add(route)
        return endpoints

    def _get_affected_data(self, nodes: List[BaseNode]) -> Set[str]:
        """Get data entities (models, tables) affected by changes."""
        data: Set[str] = set()
        for node in nodes:
            if node.node_type in (NodeType.MODEL, NodeType.TABLE, NodeType.FIELD, NodeType.COLUMN):
                data.add(self._key(node))
            # Check edges to data entities
            for edge in self.graph.get_edges_from(node):
                if edge.target and edge.target.node_type in (NodeType.MODEL, NodeType.TABLE):
                    data.add(self._key(edge.target))
        return data

    def _get_affected_files(self, nodes: List[BaseNode]) -> Set[str]:
        """Get unique file paths affected."""
        return {n.file_path for n in nodes if n.file_path}

    @staticmethod
    def _key(node: BaseNode) -> str:
        return f"{node.node_type.name}:{node.name}:{node.file_path}"
"""Architecture analyzer — detects structural/architectural changes."""

from __future__ import annotations

from typing import Dict, List, Set

from language_adapters.ir.nodes import BaseNode, NodeType
from language_adapters.ir.edges import EdgeType

from core_engine.models.semantic_graph import ValidatedSemanticGraph
from core_engine.models.evidence import ArchitectureEvidence, Signal


class ArchitectureAnalyzer:
    """Analyzes structural/architectural changes in the codebase.

    Detects:
    - New or removed dependencies
    - New database access patterns
    - New events or event handlers
    - New APIs
    - New service calls
    - New cache access
    - Cross-domain interactions
    """

    def __init__(self, graph: ValidatedSemanticGraph):
        self.graph = graph

    def analyze(self) -> ArchitectureEvidence:
        """Analyze architecture changes and return evidence."""
        new_deps = self._find_new_dependencies()
        removed_deps = self._find_removed_dependencies()
        new_db_access = self._find_new_database_access()
        new_events = self._find_new_events()
        new_apis = self._find_new_apis()
        new_service_calls = self._find_new_service_calls()
        new_cache = self._find_new_cache_access()
        cross_domain = self._find_cross_domain_interactions()

        total_changes = (
            len(new_deps) + len(removed_deps) + len(new_db_access)
            + len(new_events) + len(new_apis) + len(new_service_calls)
            + len(new_cache) + len(cross_domain)
        )

        signals = [
            Signal(
                name="ArchitectureAnalysisComplete",
                rule_name="ArchitectureAnalyzer",
                description=f"Found {total_changes} architectural changes "
                           f"({len(new_apis)} APIs, {len(new_db_access)} DB accesses, "
                           f"{len(new_events)} events, {len(cross_domain)} cross-domain)",
                properties={
                    "new_dependencies": len(new_deps),
                    "removed_dependencies": len(removed_deps),
                    "new_db_access": len(new_db_access),
                    "new_events": len(new_events),
                    "new_apis": len(new_apis),
                    "new_service_calls": len(new_service_calls),
                    "new_cache": len(new_cache),
                    "cross_domain": len(cross_domain),
                },
            )
        ]

        return ArchitectureEvidence(
            description=f"Architecture analysis: {total_changes} structural changes detected",
            signals=signals,
            confidence=0.92,
            new_dependencies=list(new_deps),
            removed_dependencies=list(removed_deps),
            new_database_access=list(new_db_access),
            new_events=list(new_events),
            new_apis=list(new_apis),
            new_service_calls=list(new_service_calls),
            new_cache_access=list(new_cache),
            cross_domain_interactions=list(cross_domain),
        )

    def _find_new_dependencies(self) -> Set[str]:
        """Find new USES edges (dependencies)."""
        new: Set[str] = set()
        for edge in self.graph.graph.get_edges(EdgeType.USES):
            if edge.change_type == "added" and edge.source and edge.target:
                new.add(f"{edge.source.name} -> {edge.target.name}")
        return new

    def _find_removed_dependencies(self) -> Set[str]:
        """Find removed USES edges (dependencies)."""
        removed: Set[str] = set()
        for edge in self.graph.graph.get_edges(EdgeType.USES):
            if edge.change_type == "removed" and edge.source and edge.target:
                removed.add(f"{edge.source.name} -> {edge.target.name}")
        return removed

    def _find_new_database_access(self) -> Set[str]:
        """Find new database read/write access patterns."""
        new: Set[str] = set()
        for edge_type in (EdgeType.WRITES, EdgeType.READS, EdgeType.CREATES, EdgeType.UPDATES, EdgeType.DELETES):
            for edge in self.graph.graph.get_edges(edge_type):
                if edge.change_type == "added" and edge.source and edge.target:
                    new.add(f"{edge.source.name} {edge_type.name} {edge.target.name}")
        return new

    def _find_new_events(self) -> Set[str]:
        """Find new events or event handlers."""
        new: Set[str] = set()
        for edge in self.graph.graph.get_edges(EdgeType.PUBLISHES):
            if edge.change_type == "added" and edge.source and edge.target:
                new.add(f"publish: {edge.source.name} -> {edge.target.name}")
        for edge in self.graph.graph.get_edges(EdgeType.SUBSCRIBES):
            if edge.change_type == "added" and edge.source and edge.target:
                new.add(f"subscribe: {edge.source.name} -> {edge.target.name}")
        return new

    def _find_new_apis(self) -> Set[str]:
        """Find new API endpoints."""
        new: Set[str] = set()
        for node in self.graph.get_nodes_by_type(NodeType.ENDPOINT):
            if node.change_type == "added":
                method = getattr(node, "method", "GET")
                route = getattr(node, "route", "?")
                new.add(f"{method} {route}")
        return new

    def _find_new_service_calls(self) -> Set[str]:
        """Find new external service calls."""
        new: Set[str] = set()
        for edge in self.graph.graph.get_edges(EdgeType.SENDS_HTTP):
            if edge.change_type == "added" and edge.source and edge.target:
                method = getattr(edge, "method", "GET")
                url = getattr(edge, "url", "?")
                new.add(f"{edge.source.name} -> {method} {url}")
        return new

    def _find_new_cache_access(self) -> Set[str]:
        """Find new cache access patterns."""
        new: Set[str] = set()
        for node in self.graph.get_nodes_by_type(NodeType.CACHE):
            if node.change_type == "added":
                op = getattr(node, "operation", "?")
                cache_type = getattr(node, "cache_type", "?")
                new.add(f"{node.name} ({op}, {cache_type})")
        return new

    def _find_cross_domain_interactions(self) -> Set[str]:
        """Find cross-domain interactions."""
        cross: Set[str] = set()
        for edge in self.graph.graph.get_edges(EdgeType.CALLS):
            if edge.change_type == "added" and edge.source and edge.target:
                src_domain = self._domain(edge.source.file_path)
                tgt_domain = self._domain(edge.target.file_path)
                if src_domain and tgt_domain and src_domain != tgt_domain:
                    cross.add(f"{edge.source.name} ({src_domain}) -> {edge.target.name} ({tgt_domain})")
        return cross

    @staticmethod
    def _domain(file_path: str) -> str:
        if not file_path:
            return ""
        return file_path.split("/")[0]
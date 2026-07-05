"""Coverage analyzer — determines test coverage of changed code."""

from __future__ import annotations

from typing import Dict, List, Set

from language_adapters.ir.nodes import BaseNode, NodeType
from language_adapters.ir.edges import EdgeType

from core_engine.models.semantic_graph import ValidatedSemanticGraph
from core_engine.models.evidence import CoverageEvidence, Signal
from core_engine.analyzers.graph_traverser import GraphTraverser


class CoverageAnalyzer:
    """Analyzes test coverage of changed code.

    Determines:
    - Which entrypoints have no test coverage
    - Which persistence paths are untested
    - Which validation logic is untested
    - Which transactions are untested
    - Which migrations are untested
    """

    def __init__(self, graph: ValidatedSemanticGraph):
        self.graph = graph
        self.traverser = GraphTraverser(graph)

    def analyze(self) -> CoverageEvidence:
        """Analyze coverage and return evidence."""
        test_nodes = self.graph.get_nodes_by_type(NodeType.TEST)
        tested_targets = self._get_tested_targets(test_nodes)

        changed_nodes = self._get_changed_nodes()
        all_node_keys = {self._key(n) for n in changed_nodes}

        untested_entrypoints = self._find_untested_entrypoints(tested_targets, all_node_keys)
        untested_persistence = self._find_untested_persistence(tested_targets, all_node_keys)
        untested_validation = self._find_untested_validation(tested_targets, all_node_keys)
        untested_transactions = self._find_untested_transactions(tested_targets, all_node_keys)
        untested_migrations = self._find_untested_migrations(tested_targets, all_node_keys)

        all_untested = (
            len(untested_entrypoints)
            + len(untested_persistence)
            + len(untested_validation)
            + len(untested_transactions)
            + len(untested_migrations)
        )

        return CoverageEvidence(
            description=f"Found {all_untested} untested code paths "
                       f"({len(untested_entrypoints)} entrypoints, "
                       f"{len(untested_persistence)} persistence paths, "
                       f"{len(untested_validation)} validation, "
                       f"{len(untested_transactions)} transactions, "
                       f"{len(untested_migrations)} migrations)",
            confidence=0.95,
            untested_entrypoints=list(untested_entrypoints),
            untested_persistence_paths=list(untested_persistence),
            untested_validation=list(untested_validation),
            untested_transactions=list(untested_transactions),
            untested_migrations=list(untested_migrations),
        )

    def _get_tested_targets(self, test_nodes: List[BaseNode]) -> Set[str]:
        """Get the set of node keys that are tested."""
        tested: Set[str] = set()
        for test_node in test_nodes:
            targets = getattr(test_node, "target_functions", [])
            tested.update(targets)
            # Also check TESTS edges
            for edge in self.graph.get_edges_from(test_node):
                if edge.edge_type == EdgeType.TESTS and edge.target:
                    tested.add(self._key(edge.target))
        return tested

    def _get_changed_nodes(self) -> List[BaseNode]:
        """Get nodes that were added or modified (not just deleted)."""
        return [
            n for n in self.graph.graph.nodes.values()
            if n.change_type in ("added", "modified")
        ]

    def _find_untested_entrypoints(
        self, tested_targets: Set[str], changed_keys: Set[str]
    ) -> List[str]:
        """Find entrypoints that are not covered by tests."""
        untested: List[str] = []
        for node in self.graph.get_nodes_by_type(NodeType.ENDPOINT):
            key = self._key(node)
            if key in changed_keys or self._is_connected_to_change(node, changed_keys):
                if key not in tested_targets:
                    # Check if the handler is tested
                    handler = getattr(node, "handler_function", "")
                    handler_tested = any(handler in t for t in tested_targets)
                    if not handler_tested:
                        untested.append(key)
        return untested

    def _find_untested_persistence(
        self, tested_targets: Set[str], changed_keys: Set[str]
    ) -> List[str]:
        """Find persistence paths that are not tested."""
        untested: List[str] = []
        for edge in self.graph.graph.get_edges(EdgeType.WRITES):
            if edge.source and self._key(edge.source) in changed_keys:
                if self._key(edge.source) not in tested_targets:
                    untested.append(self._key(edge.source))
        return untested

    def _find_untested_validation(
        self, tested_targets: Set[str], changed_keys: Set[str]
    ) -> List[str]:
        """Find validation logic that is not tested."""
        untested: List[str] = []
        for edge in self.graph.graph.get_edges(EdgeType.VALIDATES):
            if edge.source and self._key(edge.source) in changed_keys:
                if self._key(edge.source) not in tested_targets:
                    untested.append(self._key(edge.source))

        # Also check function names
        for node in self.graph.get_nodes_by_type(NodeType.FUNCTION):
            key = self._key(node)
            if key in changed_keys and self._is_validation_name(node.name):
                if key not in tested_targets:
                    untested.append(key)

        return untested

    def _find_untested_transactions(
        self, tested_targets: Set[str], changed_keys: Set[str]
    ) -> List[str]:
        """Find transaction boundaries that are not tested."""
        untested: List[str] = []
        for node in self.graph.get_nodes_by_type(NodeType.TRANSACTION):
            key = self._key(node)
            if key in changed_keys and key not in tested_targets:
                untested.append(key)
        return untested

    def _find_untested_migrations(
        self, tested_targets: Set[str], changed_keys: Set[str]
    ) -> List[str]:
        """Find migrations that are not tested."""
        untested: List[str] = []
        for node in self.graph.get_nodes_by_type(NodeType.MIGRATION):
            key = self._key(node)
            if key in changed_keys and key not in tested_targets:
                untested.append(key)
        return untested

    def _is_connected_to_change(self, node: BaseNode, changed_keys: Set[str]) -> bool:
        """Check if a node is connected to any changed node."""
        for edge in self.graph.get_edges_from(node):
            if edge.target and self._key(edge.target) in changed_keys:
                return True
        for edge in self.graph.get_edges_to(node):
            if edge.source and self._key(edge.source) in changed_keys:
                return True
        return False

    @staticmethod
    def _is_validation_name(name: str) -> bool:
        name_lower = name.lower()
        return any(
            kw in name_lower
            for kw in ["validate", "is_valid", "check", "assert", "verify"]
        )

    @staticmethod
    def _key(node: BaseNode) -> str:
        return f"{node.node_type.name}:{node.name}:{node.file_path}"
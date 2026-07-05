"""Coverage rule — detects test coverage gaps from the semantic graph."""

from __future__ import annotations

from language_adapters.ir.nodes import NodeType
from language_adapters.ir.edges import EdgeType

from core_engine.rules.base import Rule, RuleResult
from core_engine.models.semantic_graph import ValidatedSemanticGraph


class CoverageRule(Rule):
    """Detects test coverage gaps in changed code.

    This rule operates on the semantic graph directly, identifying
    which changed nodes lack corresponding test coverage.

    Signals produced:
    - UntestedEntrypoint: An entrypoint with no test coverage.
    - UntestedPersistencePath: A persistence path with no test coverage.
    - UntestedValidation: Validation logic with no test coverage.
    - UntestedTransaction: A transaction boundary with no test coverage.
    - UntestedMigration: A migration with no test coverage.
    """

    @property
    def name(self) -> str:
        return "CoverageRule"

    def execute(self, graph: ValidatedSemanticGraph) -> RuleResult:
        result = RuleResult(rule_name=self.name)

        test_nodes = graph.get_nodes_by_type(NodeType.TEST)
        tested_targets = self._get_tested_targets(graph, test_nodes)
        changed_keys = self._get_changed_keys(graph)

        # Check entrypoints
        for node in graph.get_nodes_by_type(NodeType.ENDPOINT):
            key = self._node_id(node)
            if key in changed_keys and key not in tested_targets:
                handler = getattr(node, "handler_function", "")
                handler_tested = any(handler in t for t in tested_targets)
                if not handler_tested:
                    result.signals.append(
                        self._make_signal(
                            "UntestedEntrypoint",
                            f"Entrypoint '{node.name}' has no test coverage",
                            node_ids=[key],
                            properties={
                                "method": getattr(node, "method", ""),
                                "route": getattr(node, "route", ""),
                            },
                        )
                    )

        # Check persistence writes
        for edge in graph.graph.get_edges(EdgeType.WRITES):
            if edge.source and self._node_id(edge.source) in changed_keys:
                src_key = self._node_id(edge.source)
                if src_key not in tested_targets:
                    result.signals.append(
                        self._make_signal(
                            "UntestedPersistencePath",
                            f"Persistence write by '{edge.source.name}' has no test coverage",
                            node_ids=[src_key, self._node_id(edge.target)],
                            edge_ids=[str(edge)],
                        )
                    )

        # Check validation functions
        for node in graph.get_nodes_by_type(NodeType.FUNCTION):
            key = self._node_id(node)
            if key in changed_keys and self._is_validation_name(node.name):
                if key not in tested_targets:
                    result.signals.append(
                        self._make_signal(
                            "UntestedValidation",
                            f"Validation function '{node.name}' has no test coverage",
                            node_ids=[key],
                        )
                    )

        # Check VALIDATES edges
        for edge in graph.graph.get_edges(EdgeType.VALIDATES):
            if edge.source and self._node_id(edge.source) in changed_keys:
                src_key = self._node_id(edge.source)
                if src_key not in tested_targets:
                    result.signals.append(
                        self._make_signal(
                            "UntestedValidation",
                            f"Validation logic in '{edge.source.name}' has no test coverage",
                            node_ids=[src_key],
                            edge_ids=[str(edge)],
                        )
                    )

        # Check transactions
        for node in graph.get_nodes_by_type(NodeType.TRANSACTION):
            key = self._node_id(node)
            if key in changed_keys and key not in tested_targets:
                result.signals.append(
                    self._make_signal(
                        "UntestedTransaction",
                        f"Transaction '{node.name}' has no test coverage",
                        node_ids=[key],
                    )
                )

        # Check migrations
        for node in graph.get_nodes_by_type(NodeType.MIGRATION):
            key = self._node_id(node)
            if key in changed_keys and key not in tested_targets:
                result.signals.append(
                    self._make_signal(
                        "UntestedMigration",
                        f"Migration '{node.name}' has no test coverage",
                        node_ids=[key],
                    )
                )

        return result

    def _get_tested_targets(
        self, graph: ValidatedSemanticGraph, test_nodes: list
    ) -> set[str]:
        """Get the set of node keys that are tested."""
        tested: set[str] = set()
        for test_node in test_nodes:
            targets = getattr(test_node, "target_functions", [])
            tested.update(targets)
            for edge in graph.get_edges_from(test_node):
                if edge.edge_type == EdgeType.TESTS and edge.target:
                    tested.add(self._node_id(edge.target))
        return tested

    def _get_changed_keys(self, graph: ValidatedSemanticGraph) -> set[str]:
        """Get keys of nodes that were added or modified."""
        return {
            self._node_id(n)
            for n in graph.graph.nodes.values()
            if n.change_type in ("added", "modified")
        }

    @staticmethod
    def _is_validation_name(name: str) -> bool:
        name_lower = name.lower()
        return any(
            kw in name_lower
            for kw in ["validate", "is_valid", "check", "assert", "verify", "sanitize"]
        )

    @staticmethod
    def _node_id(node) -> str:
        return f"{node.node_type.name}:{node.name}:{node.file_path}"
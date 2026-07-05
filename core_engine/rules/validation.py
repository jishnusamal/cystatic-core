"""Validation rule — detects changes to validation logic."""

from __future__ import annotations

from typing import List

from language_adapters.ir.nodes import NodeType
from language_adapters.ir.edges import EdgeType

from core_engine.rules.base import Rule, RuleResult
from core_engine.models.semantic_graph import ValidatedSemanticGraph


class ValidationRule(Rule):
    """Detects changes to validation logic.

    Signals produced:
    - ValidationModified: A validation function/method was changed.
    - ValidationAdded: New validation logic was introduced.
    - ValidationRemoved: Validation logic was removed.
    - ValidationEdgeChanged: A VALIDATES edge was added/removed/modified.
    """

    @property
    def name(self) -> str:
        return "ValidationRule"

    def execute(self, graph: ValidatedSemanticGraph) -> RuleResult:
        result = RuleResult(rule_name=self.name)

        # Check for changed validation nodes
        for node in graph.get_nodes_by_type(NodeType.FUNCTION):
            if self._is_validation_node(node):
                if node.change_type == "modified":
                    result.signals.append(
                        self._make_signal(
                            "ValidationModified",
                            f"Validation function '{node.name}' was modified.",
                            node_ids=[self._node_id(node)],
                        )
                    )
                elif node.change_type == "added":
                    result.signals.append(
                        self._make_signal(
                            "ValidationAdded",
                            f"New validation function '{node.name}' was added.",
                            node_ids=[self._node_id(node)],
                        )
                    )
                elif node.change_type == "deleted":
                    result.signals.append(
                        self._make_signal(
                            "ValidationRemoved",
                            f"Validation function '{node.name}' was removed.",
                            node_ids=[self._node_id(node)],
                        )
                    )

        # Check for changed VALIDATES edges
        for edge in graph.graph.get_edges(EdgeType.VALIDATES):
            if edge.change_type in ("added", "removed", "modified"):
                signal_name = {
                    "added": "ValidationEdgeAdded",
                    "removed": "ValidationEdgeRemoved",
                    "modified": "ValidationEdgeModified",
                }.get(edge.change_type, "ValidationEdgeChanged")

                result.signals.append(
                    self._make_signal(
                        signal_name,
                        f"Validation edge {edge.change_type}: "
                        f"{edge.source.name} -> {edge.target.name}",
                        node_ids=[self._node_id(edge.source), self._node_id(edge.target)],
                        edge_ids=[str(edge)],
                    )
                )

        return result

    def _is_validation_node(self, node) -> bool:
        """Heuristic: check if a function name suggests validation."""
        name_lower = node.name.lower()
        validation_keywords = [
            "validate", "is_valid", "check", "assert", "verify",
            "sanitize", "clean", "normalize",
        ]
        return any(kw in name_lower for kw in validation_keywords)

    @staticmethod
    def _node_id(node) -> str:
        return f"{node.node_type.name}:{node.name}:{node.file_path}"
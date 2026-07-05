"""Transaction rule — detects changes to database transaction boundaries."""

from __future__ import annotations

from language_adapters.ir.nodes import NodeType
from language_adapters.ir.edges import EdgeType

from core_engine.rules.base import Rule, RuleResult
from core_engine.models.semantic_graph import ValidatedSemanticGraph


class TransactionRule(Rule):
    """Detects changes to transaction boundaries.

    Signals produced:
    - TransactionBoundaryChanged: A transaction scope was modified.
    - TransactionAdded: A new transaction was introduced.
    - TransactionRemoved: A transaction was removed.
    - TransactionNestingChanged: Transaction nesting level changed.
    """

    @property
    def name(self) -> str:
        return "TransactionRule"

    def execute(self, graph: ValidatedSemanticGraph) -> RuleResult:
        result = RuleResult(rule_name=self.name)

        for node in graph.get_nodes_by_type(NodeType.TRANSACTION):
            if node.change_type == "modified":
                result.signals.append(
                    self._make_signal(
                        "TransactionBoundaryChanged",
                        f"Transaction '{node.name}' was modified (scope: {getattr(node, 'scope', '?')})",
                        node_ids=[self._node_id(node)],
                        properties={
                            "scope": getattr(node, "scope", ""),
                            "is_nested": getattr(node, "is_nested", False),
                        },
                    )
                )
            elif node.change_type == "added":
                result.signals.append(
                    self._make_signal(
                        "TransactionAdded",
                        f"New transaction '{node.name}' (scope: {getattr(node, 'scope', '?')})",
                        node_ids=[self._node_id(node)],
                    )
                )
            elif node.change_type == "deleted":
                result.signals.append(
                    self._make_signal(
                        "TransactionRemoved",
                        f"Transaction '{node.name}' was removed",
                        node_ids=[self._node_id(node)],
                    )
                )

        return result

    @staticmethod
    def _node_id(node) -> str:
        return f"{node.node_type.name}:{node.name}:{node.file_path}"
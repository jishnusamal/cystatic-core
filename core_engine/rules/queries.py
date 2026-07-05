"""Query rule — detects changes to database query operations."""

from __future__ import annotations

from language_adapters.ir.nodes import NodeType
from language_adapters.ir.edges import EdgeType

from core_engine.rules.base import Rule, RuleResult
from core_engine.models.semantic_graph import ValidatedSemanticGraph


class QueryRule(Rule):
    """Detects changes to database query semantics.

    Signals produced:
    - QuerySemanticsChanged: A query's filters, projections, or group_by changed.
    - QueryAdded: A new query was introduced.
    - QueryRemoved: A query was removed.
    - QueryReadAdded: A new READS edge was added.
    """

    @property
    def name(self) -> str:
        return "QueryRule"

    def execute(self, graph: ValidatedSemanticGraph) -> RuleResult:
        result = RuleResult(rule_name=self.name)

        # Check query nodes
        for node in graph.get_nodes_by_type(NodeType.QUERY):
            if node.change_type == "modified":
                changed_parts = []
                if getattr(node, "changed_filters", None):
                    changed_parts.append("filters")
                if getattr(node, "changed_group_by", None):
                    changed_parts.append("group_by")
                if getattr(node, "changed_projection", None):
                    changed_parts.append("projection")

                if changed_parts:
                    result.signals.append(
                        self._make_signal(
                            "QuerySemanticsChanged",
                            f"Query '{node.name}' changed: {', '.join(changed_parts)}",
                            node_ids=[self._node_id(node)],
                            properties={"changed_parts": changed_parts},
                        )
                    )
            elif node.change_type == "added":
                result.signals.append(
                    self._make_signal(
                        "QueryAdded",
                        f"New query '{node.name}' targeting {getattr(node, 'target_model', '?')}",
                        node_ids=[self._node_id(node)],
                    )
                )
            elif node.change_type == "deleted":
                result.signals.append(
                    self._make_signal(
                        "QueryRemoved",
                        f"Query '{node.name}' was removed",
                        node_ids=[self._node_id(node)],
                    )
                )

        # Check READS edges (database reads)
        for edge in graph.graph.get_edges(EdgeType.READS):
            if edge.change_type in ("added", "removed"):
                result.signals.append(
                    self._make_signal(
                        "QueryReadAdded" if edge.change_type == "added" else "QueryReadRemoved",
                        f"Database read {edge.change_type}: {edge.source.name} reads {edge.target.name}",
                        node_ids=[self._node_id(edge.source), self._node_id(edge.target)],
                        edge_ids=[str(edge)],
                    )
                )

        return result

    @staticmethod
    def _node_id(node) -> str:
        return f"{node.node_type.name}:{node.name}:{node.file_path}"
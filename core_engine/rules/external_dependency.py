"""External dependency rule — detects changes to external service dependencies."""

from __future__ import annotations

from language_adapters.ir.nodes import NodeType
from language_adapters.ir.edges import EdgeType

from core_engine.rules.base import Rule, RuleResult
from core_engine.models.semantic_graph import ValidatedSemanticGraph


class ExternalDependencyRule(Rule):
    """Detects changes to external service dependencies.

    Signals produced:
    - NewExternalDependency: A new external service call was added.
    - ExternalDependencyRemoved: An external service call was removed.
    - ExternalDependencyChanged: An external service call was modified.
    """

    @property
    def name(self) -> str:
        return "ExternalDependencyRule"

    def execute(self, graph: ValidatedSemanticGraph) -> RuleResult:
        result = RuleResult(rule_name=self.name)

        # Check EXTERNAL_SERVICE nodes
        for node in graph.get_nodes_by_type(NodeType.EXTERNAL_SERVICE):
            if node.change_type == "added":
                result.signals.append(
                    self._make_signal(
                        "NewExternalDependency",
                        f"New external dependency: '{node.name}' "
                        f"(type: {getattr(node, 'service_type', '?')})",
                        node_ids=[self._node_id(node)],
                        properties={
                            "service_type": getattr(node, "service_type", ""),
                            "protocol": getattr(node, "protocol", ""),
                        },
                    )
                )
            elif node.change_type == "deleted":
                result.signals.append(
                    self._make_signal(
                        "ExternalDependencyRemoved",
                        f"External dependency removed: '{node.name}'",
                        node_ids=[self._node_id(node)],
                    )
                )
            elif node.change_type == "modified":
                result.signals.append(
                    self._make_signal(
                        "ExternalDependencyChanged",
                        f"External dependency modified: '{node.name}'",
                        node_ids=[self._node_id(node)],
                    )
                )

        return result

    @staticmethod
    def _node_id(node) -> str:
        return f"{node.node_type.name}:{node.name}:{node.file_path}"
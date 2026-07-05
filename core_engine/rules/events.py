"""Event rule — detects changes to event publishing/subscribing."""

from __future__ import annotations

from language_adapters.ir.nodes import NodeType
from language_adapters.ir.edges import EdgeType

from core_engine.rules.base import Rule, RuleResult
from core_engine.models.semantic_graph import ValidatedSemanticGraph


class EventRule(Rule):
    """Detects changes to event publishing and subscribing.

    Signals produced:
    - NewEventPublished: A new event publish was added.
    - NewEventSubscribed: A new event subscription was added.
    - EventRemoved: An event publish/subscribe was removed.
    """

    @property
    def name(self) -> str:
        return "EventRule"

    def execute(self, graph: ValidatedSemanticGraph) -> RuleResult:
        result = RuleResult(rule_name=self.name)

        # Check event nodes
        for node in graph.get_nodes_by_type(NodeType.EVENT):
            if node.change_type == "added":
                result.signals.append(
                    self._make_signal(
                        "NewEventPublished",
                        f"New event: '{node.name}' (type: {getattr(node, 'event_type', '?')})",
                        node_ids=[self._node_id(node)],
                    )
                )
            elif node.change_type == "deleted":
                result.signals.append(
                    self._make_signal(
                        "EventRemoved",
                        f"Event removed: '{node.name}'",
                        node_ids=[self._node_id(node)],
                    )
                )

        # Check PUBLISHES edges
        for edge in graph.graph.get_edges(EdgeType.PUBLISHES):
            if edge.change_type in ("added", "removed"):
                result.signals.append(
                    self._make_signal(
                        "NewEventPublished" if edge.change_type == "added" else "EventRemoved",
                        f"Event publish {edge.change_type}: {edge.source.name} publishes to {edge.target.name}",
                        node_ids=[self._node_id(edge.source), self._node_id(edge.target)],
                        edge_ids=[str(edge)],
                    )
                )

        # Check SUBSCRIBES edges
        for edge in graph.graph.get_edges(EdgeType.SUBSCRIBES):
            if edge.change_type in ("added", "removed"):
                result.signals.append(
                    self._make_signal(
                        "NewEventSubscribed" if edge.change_type == "added" else "EventSubscriptionRemoved",
                        f"Event subscription {edge.change_type}: {edge.source.name} subscribes to {edge.target.name}",
                        node_ids=[self._node_id(edge.source), self._node_id(edge.target)],
                        edge_ids=[str(edge)],
                    )
                )

        # Check EMITS_EVENT edges
        for edge in graph.graph.get_edges(EdgeType.EMITS_EVENT):
            if edge.change_type in ("added", "removed"):
                result.signals.append(
                    self._make_signal(
                        "NewEventPublished" if edge.change_type == "added" else "EventRemoved",
                        f"Event emission {edge.change_type}: {edge.source.name} emits {edge.target.name}",
                        node_ids=[self._node_id(edge.source), self._node_id(edge.target)],
                        edge_ids=[str(edge)],
                    )
                )

        return result

    @staticmethod
    def _node_id(node) -> str:
        return f"{node.node_type.name}:{node.name}:{node.file_path}"
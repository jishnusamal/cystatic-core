"""API exposure rule — detects changes to HTTP API endpoints."""

from __future__ import annotations

from language_adapters.ir.nodes import NodeType
from language_adapters.ir.edges import EdgeType

from core_engine.rules.base import Rule, RuleResult
from core_engine.models.semantic_graph import ValidatedSemanticGraph


class APIExposureRule(Rule):
    """Detects changes to API endpoints and their exposure.

    Signals produced:
    - NewAPIEndpoint: A new HTTP endpoint was added.
    - APIModified: An existing endpoint was modified.
    - APIRemoved: An endpoint was removed.
    - NewExternalCall: A new external HTTP call was added.
    """

    @property
    def name(self) -> str:
        return "APIExposureRule"

    def execute(self, graph: ValidatedSemanticGraph) -> RuleResult:
        result = RuleResult(rule_name=self.name)

        # Check endpoint nodes
        for node in graph.get_nodes_by_type(NodeType.ENDPOINT):
            if node.change_type == "added":
                result.signals.append(
                    self._make_signal(
                        "NewAPIEndpoint",
                        f"New endpoint: {getattr(node, 'method', 'GET')} {getattr(node, 'route', '?')} "
                        f"(handler: {getattr(node, 'handler_function', '?')})",
                        node_ids=[self._node_id(node)],
                        properties={
                            "method": getattr(node, "method", ""),
                            "route": getattr(node, "route", ""),
                            "framework": getattr(node, "framework", ""),
                        },
                    )
                )
            elif node.change_type == "modified":
                result.signals.append(
                    self._make_signal(
                        "APIModified",
                        f"Endpoint modified: {getattr(node, 'method', 'GET')} {getattr(node, 'route', '?')}",
                        node_ids=[self._node_id(node)],
                    )
                )
            elif node.change_type == "deleted":
                result.signals.append(
                    self._make_signal(
                        "APIRemoved",
                        f"Endpoint removed: {getattr(node, 'method', 'GET')} {getattr(node, 'route', '?')}",
                        node_ids=[self._node_id(node)],
                    )
                )

        # Check EXPOSES edges
        for edge in graph.graph.get_edges(EdgeType.EXPOSES):
            if edge.change_type in ("added", "removed"):
                result.signals.append(
                    self._make_signal(
                        "APIExposureAdded" if edge.change_type == "added" else "APIExposureRemoved",
                        f"API exposure {edge.change_type}: {edge.source.name} exposes {edge.target.name}",
                        node_ids=[self._node_id(edge.source), self._node_id(edge.target)],
                        edge_ids=[str(edge)],
                    )
                )

        # Check SENDS_HTTP edges (outgoing HTTP calls)
        for edge in graph.graph.get_edges(EdgeType.SENDS_HTTP):
            if edge.change_type in ("added", "removed"):
                result.signals.append(
                    self._make_signal(
                        "NewExternalCall" if edge.change_type == "added" else "ExternalCallRemoved",
                        f"External HTTP call {edge.change_type}: {edge.source.name} -> "
                        f"{getattr(edge, 'method', 'GET')} {getattr(edge, 'url', '?')}",
                        node_ids=[self._node_id(edge.source), self._node_id(edge.target)],
                        edge_ids=[str(edge)],
                    )
                )

        return result

    @staticmethod
    def _node_id(node) -> str:
        return f"{node.node_type.name}:{node.name}:{node.file_path}"
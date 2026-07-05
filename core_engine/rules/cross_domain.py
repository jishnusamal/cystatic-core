"""Cross-domain rule — detects interactions across domain boundaries."""

from __future__ import annotations

from language_adapters.ir.nodes import NodeType
from language_adapters.ir.edges import EdgeType

from core_engine.rules.base import Rule, RuleResult
from core_engine.models.semantic_graph import ValidatedSemanticGraph


class CrossDomainRule(Rule):
    """Detects cross-domain interactions.

    A "domain" is inferred from the file path structure.
    Cross-domain interactions occur when code in one directory
    references code in a different top-level directory.

    Signals produced:
    - CrossDomainInteraction: A cross-domain call was added/removed.
    - NewServiceCall: A new cross-service call was added.
    """

    @property
    def name(self) -> str:
        return "CrossDomainRule"

    def execute(self, graph: ValidatedSemanticGraph) -> RuleResult:
        result = RuleResult(rule_name=self.name)

        # Check CALLS edges for cross-domain interactions
        for edge in graph.graph.get_edges(EdgeType.CALLS):
            if edge.change_type in ("added", "removed"):
                source_domain = self._extract_domain(edge.source.file_path)
                target_domain = self._extract_domain(edge.target.file_path)

                if source_domain and target_domain and source_domain != target_domain:
                    result.signals.append(
                        self._make_signal(
                            "CrossDomainInteraction",
                            f"Cross-domain call {edge.change_type}: "
                            f"{edge.source.name} ({source_domain}) -> "
                            f"{edge.target.name} ({target_domain})",
                            node_ids=[
                                self._node_id(edge.source),
                                self._node_id(edge.target),
                            ],
                            edge_ids=[str(edge)],
                            properties={
                                "source_domain": source_domain,
                                "target_domain": target_domain,
                            },
                        )
                    )

        # Check USES edges for cross-domain dependencies
        for edge in graph.graph.get_edges(EdgeType.USES):
            if edge.change_type in ("added", "removed"):
                source_domain = self._extract_domain(edge.source.file_path)
                target_domain = self._extract_domain(edge.target.file_path)

                if source_domain and target_domain and source_domain != target_domain:
                    result.signals.append(
                        self._make_signal(
                            "CrossDomainInteraction",
                            f"Cross-domain dependency {edge.change_type}: "
                            f"{edge.source.name} ({source_domain}) uses "
                            f"{edge.target.name} ({target_domain})",
                            node_ids=[
                                self._node_id(edge.source),
                                self._node_id(edge.target),
                            ],
                            edge_ids=[str(edge)],
                            properties={
                                "source_domain": source_domain,
                                "target_domain": target_domain,
                            },
                        )
                    )

        return result

    @staticmethod
    def _extract_domain(file_path: str) -> str:
        """Extract the top-level domain from a file path."""
        if not file_path:
            return ""
        parts = file_path.split("/")
        return parts[0] if parts else ""

    @staticmethod
    def _node_id(node) -> str:
        return f"{node.node_type.name}:{node.name}:{node.file_path}"
"""Persistence rule — detects changes to database write operations."""

from __future__ import annotations

from language_adapters.ir.nodes import NodeType
from language_adapters.ir.edges import EdgeType

from core_engine.rules.base import Rule, RuleResult
from core_engine.models.semantic_graph import ValidatedSemanticGraph


class PersistenceRule(Rule):
    """Detects changes to persistence (database write) operations.

    Signals produced:
    - PersistenceWriteAdded: A new WRITES edge was added.
    - PersistenceWriteRemoved: A WRITES edge was removed.
    - PersistenceWriteModified: A WRITES edge was modified.
    - ModelFieldChanged: A model field was added/removed/modified.
    """

    @property
    def name(self) -> str:
        return "PersistenceRule"

    def execute(self, graph: ValidatedSemanticGraph) -> RuleResult:
        result = RuleResult(rule_name=self.name)

        # Check WRITES edges
        for edge in graph.graph.get_edges(EdgeType.WRITES):
            if edge.change_type in ("added", "removed", "modified"):
                signal_name = {
                    "added": "PersistenceWriteAdded",
                    "removed": "PersistenceWriteRemoved",
                    "modified": "PersistenceWriteModified",
                }.get(edge.change_type, "PersistenceWriteChanged")

                result.signals.append(
                    self._make_signal(
                        signal_name,
                        f"Persistence write {edge.change_type}: "
                        f"{edge.source.name} writes to {edge.target.name}",
                        node_ids=[self._node_id(edge.source), self._node_id(edge.target)],
                        edge_ids=[str(edge)],
                    )
                )

        # Check CREATES edges (object creation that persists)
        for edge in graph.graph.get_edges(EdgeType.CREATES):
            if edge.change_type in ("added", "removed"):
                result.signals.append(
                    self._make_signal(
                        "PersistenceCreateAdded" if edge.change_type == "added" else "PersistenceCreateRemoved",
                        f"Object creation {edge.change_type}: "
                        f"{edge.source.name} creates {edge.target.name}",
                        node_ids=[self._node_id(edge.source), self._node_id(edge.target)],
                        edge_ids=[str(edge)],
                    )
                )

        # Check UPDATES edges
        for edge in graph.graph.get_edges(EdgeType.UPDATES):
            if edge.change_type in ("added", "removed"):
                result.signals.append(
                    self._make_signal(
                        "PersistenceUpdateAdded" if edge.change_type == "added" else "PersistenceUpdateRemoved",
                        f"Update operation {edge.change_type}: "
                        f"{edge.source.name} updates {edge.target.name}",
                        node_ids=[self._node_id(edge.source), self._node_id(edge.target)],
                        edge_ids=[str(edge)],
                    )
                )

        # Check DELETES edges
        for edge in graph.graph.get_edges(EdgeType.DELETES):
            if edge.change_type in ("added", "removed"):
                result.signals.append(
                    self._make_signal(
                        "PersistenceDeleteAdded" if edge.change_type == "added" else "PersistenceDeleteRemoved",
                        f"Delete operation {edge.change_type}: "
                        f"{edge.source.name} deletes {edge.target.name}",
                        node_ids=[self._node_id(edge.source), self._node_id(edge.target)],
                        edge_ids=[str(edge)],
                    )
                )

        # Check model/field changes
        for node in graph.get_nodes_by_type(NodeType.MODEL):
            if node.change_type in ("added", "deleted", "modified"):
                result.signals.append(
                    self._make_signal(
                        f"Model{node.change_type.capitalize()}",
                        f"Model '{node.name}' was {node.change_type}.",
                        node_ids=[self._node_id(node)],
                    )
                )

        for node in graph.get_nodes_by_type(NodeType.FIELD):
            if node.change_type in ("added", "deleted", "modified"):
                result.signals.append(
                    self._make_signal(
                        f"Field{node.change_type.capitalize()}",
                        f"Field '{node.name}' on model '{getattr(node, 'model_name', '?')}' was {node.change_type}.",
                        node_ids=[self._node_id(node)],
                    )
                )

        return result

    @staticmethod
    def _node_id(node) -> str:
        return f"{node.node_type.name}:{node.name}:{node.file_path}"
"""Migration rule — detects changes to database migrations."""

from __future__ import annotations

from language_adapters.ir.nodes import NodeType
from language_adapters.ir.edges import EdgeType

from core_engine.rules.base import Rule, RuleResult
from core_engine.models.semantic_graph import ValidatedSemanticGraph


class MigrationRule(Rule):
    """Detects changes to database migrations.

    Signals produced:
    - MigrationAdded: A new migration was added.
    - MigrationWithoutBackfill: A migration that may need a data backfill.
    - MigrationDestructive: A destructive migration (drop column/table).
    - MigrationModified: An existing migration was modified.
    """

    @property
    def name(self) -> str:
        return "MigrationRule"

    def execute(self, graph: ValidatedSemanticGraph) -> RuleResult:
        result = RuleResult(rule_name=self.name)

        for node in graph.get_nodes_by_type(NodeType.MIGRATION):
            if node.change_type == "added":
                operations = getattr(node, "operations", [])
                has_destructive = any(
                    op.get("type") in ("drop_column", "drop_table", "alter_column")
                    for op in operations
                )
                has_data_migration = any(
                    op.get("type") in ("add_column", "alter_column")
                    for op in operations
                )

                result.signals.append(
                    self._make_signal(
                        "MigrationAdded",
                        f"New migration '{node.name}' with {len(operations)} operations",
                        node_ids=[self._node_id(node)],
                        properties={
                            "operation_count": len(operations),
                            "has_destructive": has_destructive,
                            "has_data_migration": has_data_migration,
                        },
                    )
                )

                if has_data_migration:
                    result.signals.append(
                        self._make_signal(
                            "MigrationWithoutBackfill",
                            f"Migration '{node.name}' may need a data backfill",
                            node_ids=[self._node_id(node)],
                        )
                    )

                if has_destructive:
                    result.signals.append(
                        self._make_signal(
                            "MigrationDestructive",
                            f"Migration '{node.name}' contains destructive operations",
                            node_ids=[self._node_id(node)],
                        )
                    )

            elif node.change_type == "modified":
                result.signals.append(
                    self._make_signal(
                        "MigrationModified",
                        f"Migration '{node.name}' was modified",
                        node_ids=[self._node_id(node)],
                    )
                )

        # Check MIGRATES edges
        for edge in graph.graph.get_edges(EdgeType.MIGRATES):
            if edge.change_type in ("added", "removed"):
                result.signals.append(
                    self._make_signal(
                        "MigrationEdgeAdded" if edge.change_type == "added" else "MigrationEdgeRemoved",
                        f"Migration edge {edge.change_type}: {edge.source.name} -> {edge.target.name}",
                        node_ids=[self._node_id(edge.source), self._node_id(edge.target)],
                        edge_ids=[str(edge)],
                    )
                )

        return result

    @staticmethod
    def _node_id(node) -> str:
        return f"{node.node_type.name}:{node.name}:{node.file_path}"
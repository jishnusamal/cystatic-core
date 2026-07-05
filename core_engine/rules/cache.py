"""Cache rule — detects changes to caching operations."""

from __future__ import annotations

from language_adapters.ir.nodes import NodeType
from language_adapters.ir.edges import EdgeType

from core_engine.rules.base import Rule, RuleResult
from core_engine.models.semantic_graph import ValidatedSemanticGraph


class CacheRule(Rule):
    """Detects changes to caching operations.

    Signals produced:
    - CacheWriteAdded: A new cache write was added.
    - CacheWriteRemoved: A cache write was removed.
    - CacheInvalidationAdded: A new cache invalidation was added.
    - CacheAccessChanged: A cache read operation changed.
    """

    @property
    def name(self) -> str:
        return "CacheRule"

    def execute(self, graph: ValidatedSemanticGraph) -> RuleResult:
        result = RuleResult(rule_name=self.name)

        # Check CACHE nodes
        for node in graph.get_nodes_by_type(NodeType.CACHE):
            operation = getattr(node, "operation", "")
            if node.change_type == "added":
                signal_name = "CacheWriteAdded" if operation == "set" else "CacheAccessChanged"
                result.signals.append(
                    self._make_signal(
                        signal_name,
                        f"New cache operation: '{node.name}' ({operation}) "
                        f"type: {getattr(node, 'cache_type', '?')}",
                        node_ids=[self._node_id(node)],
                        properties={
                            "operation": operation,
                            "cache_type": getattr(node, "cache_type", ""),
                        },
                    )
                )
            elif node.change_type == "deleted":
                result.signals.append(
                    self._make_signal(
                        "CacheWriteRemoved" if operation == "set" else "CacheAccessChanged",
                        f"Cache operation removed: '{node.name}' ({operation})",
                        node_ids=[self._node_id(node)],
                    )
                )
            elif node.change_type == "modified":
                result.signals.append(
                    self._make_signal(
                        "CacheAccessChanged",
                        f"Cache operation modified: '{node.name}' ({operation})",
                        node_ids=[self._node_id(node)],
                    )
                )

        return result

    @staticmethod
    def _node_id(node) -> str:
        return f"{node.node_type.name}:{node.name}:{node.file_path}"
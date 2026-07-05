"""Auth rule — detects changes to authentication/authorization logic."""

from __future__ import annotations

from language_adapters.ir.nodes import NodeType
from language_adapters.ir.edges import EdgeType

from core_engine.rules.base import Rule, RuleResult
from core_engine.models.semantic_graph import ValidatedSemanticGraph


class AuthRule(Rule):
    """Detects changes to authentication/authorization.

    Signals produced:
    - AuthLogicChanged: Auth-related code was modified.
    - AuthAdded: New auth logic was introduced.
    - AuthRemoved: Auth logic was removed.
    - EndpointAuthChanged: An endpoint's auth protection changed.
    """

    @property
    def name(self) -> str:
        return "AuthRule"

    def execute(self, graph: ValidatedSemanticGraph) -> RuleResult:
        result = RuleResult(rule_name=self.name)

        # Check functions/methods with auth-related names
        for node_type in (NodeType.FUNCTION, NodeType.METHOD):
            for node in graph.get_nodes_by_type(node_type):
                if self._is_auth_node(node):
                    if node.change_type == "modified":
                        result.signals.append(
                            self._make_signal(
                                "AuthLogicChanged",
                                f"Auth function '{node.name}' was modified",
                                node_ids=[self._node_id(node)],
                            )
                        )
                    elif node.change_type == "added":
                        result.signals.append(
                            self._make_signal(
                                "AuthAdded",
                                f"New auth function '{node.name}' was added",
                                node_ids=[self._node_id(node)],
                            )
                        )
                    elif node.change_type == "deleted":
                        result.signals.append(
                            self._make_signal(
                                "AuthRemoved",
                                f"Auth function '{node.name}' was removed",
                                node_ids=[self._node_id(node)],
                            )
                        )

        # Check decorators that are auth-related
        for node in graph.get_nodes_by_type(NodeType.DECORATOR):
            if self._is_auth_decorator(node):
                if node.change_type == "added":
                    result.signals.append(
                        self._make_signal(
                            "AuthAdded",
                            f"Auth decorator '{node.name}' was added on {getattr(node, 'target_name', '?')}",
                            node_ids=[self._node_id(node)],
                        )
                    )
                elif node.change_type == "removed":
                    result.signals.append(
                        self._make_signal(
                            "AuthRemoved",
                            f"Auth decorator '{node.name}' was removed from {getattr(node, 'target_name', '?')}",
                            node_ids=[self._node_id(node)],
                        )
                    )

        return result

    def _is_auth_node(self, node) -> bool:
        name_lower = node.name.lower()
        auth_keywords = [
            "login", "logout", "authenticate", "authorize", "permission",
            "role", "rbac", "jwt", "token", "session", "auth",
            "require_auth", "login_required", "permission_required",
        ]
        return any(kw in name_lower for kw in auth_keywords)

    def _is_auth_decorator(self, node) -> bool:
        name_lower = node.name.lower()
        auth_decorators = [
            "login_required", "permission_required", "auth_required",
            "require_auth", "has_role", "has_permission",
        ]
        return any(kw in name_lower for kw in auth_decorators)

    @staticmethod
    def _node_id(node) -> str:
        return f"{node.node_type.name}:{node.name}:{node.file_path}"
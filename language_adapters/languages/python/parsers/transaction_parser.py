"""Transaction parser — detects transaction boundaries.

Detects:
    transaction.atomic, atomic decorator, commit, rollback, flush,
    savepoint, session.begin()
"""

from __future__ import annotations

import ast
from typing import Any, Dict, List, Optional, Set

from language_adapters.ir import (
    SemanticGraph,
    NodeType,
    TransactionNode,
    FunctionNode,
    UsesEdge,
)
from language_adapters.interfaces.graph import GraphBuilder
from language_adapters.shared.graph_builder import GraphBuilderUtils as G


class TransactionParser(GraphBuilder):
    """Extracts transaction boundaries from function bodies."""

    _TRANSACTION_ATTRS: Set[str] = {
        "atomic", "commit", "rollback", "flush", "savepoint",
        "commit_manually", "set_rollback", "savepoint_rollback",
    }

    _TRANSACTION_FUNCS: Set[str] = {
        "begin", "commit", "rollback", "flush", "savepoint",
    }

    def build(self, graph: SemanticGraph, context: Dict[str, Any]) -> SemanticGraph:
        tree: Optional[ast.Module] = context.get("tree")
        file_path: str = context.get("file_path", "")

        if tree is None:
            return graph

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._extract_transactions(node, graph, file_path)

        return graph

    def _extract_transactions(
        self,
        func_node: ast.FunctionDef | ast.AsyncFunctionDef,
        graph: SemanticGraph,
        file_path: str,
    ) -> None:
        caller = G.ensure_function(graph, func_node.name, file_path)

        # Check decorators for @transaction.atomic
        for dec in func_node.decorator_list:
            if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute):
                if dec.func.attr == "atomic":
                    tx = TransactionNode(
                        name=f"{func_node.name}.atomic",
                        file_path=file_path,
                        scope="decorator",
                    )
                    graph.add_node(tx)
                    graph.add_edge(UsesEdge(source=caller, target=tx))

        # Check body for transaction calls
        for child in ast.walk(func_node):
            if isinstance(child, ast.Call):
                self._process_call(child, caller, graph, file_path)

    def _process_call(
        self,
        call: ast.Call,
        caller: FunctionNode,
        graph: SemanticGraph,
        file_path: str,
    ) -> None:
        func = call.func

        # transaction.atomic(), session.begin(), etc.
        if isinstance(func, ast.Attribute):
            attr = func.attr

            if attr in self._TRANSACTION_ATTRS:
                tx_name = f"{ast.unparse(func.value)}.{attr}"
                tx = TransactionNode(
                    name=tx_name,
                    file_path=file_path,
                    scope="context_manager" if attr == "atomic" else "call",
                )
                graph.add_node(tx)
                graph.add_edge(UsesEdge(source=caller, target=tx))

        # Direct function calls: begin(), commit()
        elif isinstance(func, ast.Name):
            if func.id in self._TRANSACTION_FUNCS:
                tx = TransactionNode(
                    name=func.id,
                    file_path=file_path,
                    scope="call",
                )
                graph.add_node(tx)
                graph.add_edge(UsesEdge(source=caller, target=tx))
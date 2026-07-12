"""Control flow parser — extracts control flow information.

Extracts:
    return, yield, raise, try, except, finally, continue, break,
    loop, async, await
"""

from __future__ import annotations

import ast
from typing import Any, Dict, List, Optional

from language_adapters.ir import (
    SemanticGraph,
    NodeType,
    FunctionNode,
    UsesEdge,
)
from language_adapters.interfaces.graph import GraphBuilder
from language_adapters.shared.graph_builder import GraphBuilderUtils as G


class ControlFlowParser(GraphBuilder):
    """Extracts control flow information from function bodies."""

    def build(self, graph: SemanticGraph, context: Dict[str, Any]) -> SemanticGraph:
        tree: Optional[ast.Module] = context.get("tree")
        file_path: str = context.get("file_path", "")

        if tree is None:
            return graph

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._extract_control_flow(node, graph, file_path)

        return graph

    def _extract_control_flow(
        self,
        func_node: ast.FunctionDef | ast.AsyncFunctionDef,
        graph: SemanticGraph,
        file_path: str,
    ) -> None:
        caller = G.ensure_function(graph, func_node.name, file_path)

        has_exception_path = False
        has_loop = False
        has_yield = False
        has_await = False

        for child in ast.walk(func_node):
            if isinstance(child, ast.Try):
                has_exception_path = True

            if isinstance(child, (ast.For, ast.While, ast.AsyncFor)):
                has_loop = True

            if isinstance(child, ast.Yield):
                has_yield = True

            if isinstance(child, ast.Await):
                has_await = True

        if has_exception_path:
            exc_node = FunctionNode(
                name=f"{func_node.name}.exception_path",
                file_path=file_path,
            )
            graph.add_node(exc_node)
            graph.add_edge(
                UsesEdge(
                    source=caller,
                    target=exc_node,
                    properties={"type": "exception_path"},
                )
            )

        if has_loop:
            loop_node = FunctionNode(
                name=f"{func_node.name}.loop",
                file_path=file_path,
            )
            graph.add_node(loop_node)
            graph.add_edge(
                UsesEdge(
                    source=caller,
                    target=loop_node,
                    properties={"type": "loop"},
                )
            )

        if has_yield:
            yield_node = FunctionNode(
                name=f"{func_node.name}.generator",
                file_path=file_path,
            )
            graph.add_node(yield_node)
            graph.add_edge(
                UsesEdge(
                    source=caller,
                    target=yield_node,
                    properties={"type": "generator"},
                )
            )

        if has_await:
            await_node = FunctionNode(
                name=f"{func_node.name}.async",
                file_path=file_path,
            )
            graph.add_node(await_node)
            graph.add_edge(
                UsesEdge(
                    source=caller,
                    target=await_node,
                    properties={"type": "async"},
                )
            )
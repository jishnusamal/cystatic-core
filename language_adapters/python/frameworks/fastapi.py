"""FastAPI endpoint parser — produces EndpointNode with EXPOSES edges.

Moved from the old FastAPIEndpointParser in python_adapter.py.
Instead of returning dicts, produces EndpointNode and EXPOSES edges.
"""

from __future__ import annotations

import ast
from typing import Any, Dict, List, Optional, Set

from language_adapters.ir import (
    SemanticGraph,
    NodeType,
    EndpointNode,
    FunctionNode,
    ExposesEdge,
)
from language_adapters.interfaces.graph import GraphBuilder
from language_adapters.shared.graph_builder import GraphBuilderUtils as G


class FastAPIParser(GraphBuilder):
    """Extracts FastAPI endpoints and adds them to the semantic graph."""

    _HTTP_METHODS: Set[str] = {
        "get", "post", "put", "delete", "patch", "options", "head",
    }

    def build(self, graph: SemanticGraph, context: Dict[str, Any]) -> SemanticGraph:
        tree: Optional[ast.Module] = context.get("tree")
        file_path: str = context.get("file_path", "")

        if tree is None:
            return graph

        if not self._is_fastapi_file(tree):
            return graph

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._extract_endpoint(node, graph, file_path)

        return graph

    def _is_fastapi_file(self, tree: ast.Module) -> bool:
        """Check if the file imports FastAPI."""
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module == "fastapi":
                    return True
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for dec in node.decorator_list:
                    if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute):
                        if dec.func.attr in self._HTTP_METHODS:
                            return True
        return False

    def _extract_endpoint(
        self,
        func_node: ast.FunctionDef | ast.AsyncFunctionDef,
        graph: SemanticGraph,
        file_path: str,
    ) -> None:
        for decorator in func_node.decorator_list:
            method, route = self._extract_route(decorator)
            if method and route:
                endpoint = G.ensure_endpoint(
                    graph, method.upper(), route, file_path,
                    framework="fastapi",
                    handler_function=func_node.name,
                )

                # Add EXPOSES edge to the handler function
                handler = G.ensure_function(graph, func_node.name, file_path)
                graph.add_edge(ExposesEdge(source=endpoint, target=handler))

    def _extract_route(self, decorator: ast.expr) -> tuple[Optional[str], Optional[str]]:
        if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute):
            method = decorator.func.attr
            if method in self._HTTP_METHODS:
                route = self._get_route_from_args(decorator)
                return method, route
        return None, None

    @staticmethod
    def _get_route_from_args(decorator: ast.Call) -> Optional[str]:
        if not decorator.args:
            return None
        arg = decorator.args[0]
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            return arg.value
        return None
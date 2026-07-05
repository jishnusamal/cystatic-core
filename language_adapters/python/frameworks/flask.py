"""Flask endpoint parser — produces EndpointNode with EXPOSES edges.

Moved from the old FlaskEndpointParser in python_adapter.py.
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


class FlaskParser(GraphBuilder):
    """Extracts Flask endpoints and adds them to the semantic graph."""

    _HTTP_METHODS: Set[str] = {
        "get", "post", "put", "delete", "patch", "options", "head",
    }

    def build(self, graph: SemanticGraph, context: Dict[str, Any]) -> SemanticGraph:
        tree: Optional[ast.Module] = context.get("tree")
        file_path: str = context.get("file_path", "")

        if tree is None:
            return graph

        if not self._is_flask_file(tree):
            return graph

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._extract_endpoint(node, graph, file_path)

        return graph

    def _is_flask_file(self, tree: ast.Module) -> bool:
        """Check if the file imports Flask."""
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module == "flask":
                    return True
            if isinstance(node, ast.Import):
                if any(alias.name == "flask" for alias in node.names):
                    return True
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for dec in node.decorator_list:
                    if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute):
                        if dec.func.attr == "route":
                            return True
        return False

    def _extract_endpoint(
        self,
        func_node: ast.FunctionDef | ast.AsyncFunctionDef,
        graph: SemanticGraph,
        file_path: str,
    ) -> None:
        for decorator in func_node.decorator_list:
            route, methods = self._extract_route_and_methods(decorator)
            if route:
                method_str = ",".join(methods) if methods else "GET"
                endpoint = G.ensure_endpoint(
                    graph, method_str, route, file_path,
                    framework="flask",
                    handler_function=func_node.name,
                )

                # Add EXPOSES edge to the handler function
                handler = G.ensure_function(graph, func_node.name, file_path)
                graph.add_edge(ExposesEdge(source=endpoint, target=handler))

    def _extract_route_and_methods(
        self,
        decorator: ast.expr,
    ) -> tuple[Optional[str], List[str]]:
        if not (isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute)):
            return None, []
        if decorator.func.attr != "route":
            return None, []

        route = self._get_route_from_args(decorator)
        methods = self._get_methods_from_keywords(decorator)
        return route, methods

    @staticmethod
    def _get_route_from_args(decorator: ast.Call) -> Optional[str]:
        if not decorator.args:
            return None
        arg = decorator.args[0]
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            return arg.value
        return None

    @staticmethod
    def _get_methods_from_keywords(decorator: ast.Call) -> List[str]:
        for kw in decorator.keywords:
            if kw.arg != "methods":
                continue
            if isinstance(kw.value, (ast.List, ast.Tuple)):
                methods: List[str] = []
                for elt in kw.value.elts:
                    if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                        method = elt.value.lower()
                        if method in {"get", "post", "put", "delete", "patch", "options", "head"}:
                            methods.append(method.upper())
                if methods:
                    return methods
        return ["GET"]
"""Query parser — detects database query operations and produces QueryNode.

Detects:
    filter(), exclude(), annotate(), aggregate(), count(), exists(),
    join(), prefetch_related(), select_related(), order_by(), distinct(),
    values(), raw SQL, execute(), cursor(), text()
"""

from __future__ import annotations

import ast
import re
from typing import Any, Dict, List, Optional, Set

from language_adapters.ir import (
    SemanticGraph,
    NodeType,
    QueryNode,
    FunctionNode,
    UsesEdge,
)
from language_adapters.interfaces.graph import GraphBuilder
from language_adapters.shared.graph_builder import GraphBuilderUtils as G


class QueryParser(GraphBuilder):
    """Extracts database query operations and produces QueryNode."""

    _QUERY_METHODS: Set[str] = {
        "filter", "exclude", "annotate", "aggregate", "count", "exists",
        "prefetch_related", "select_related", "order_by", "distinct",
        "values", "values_list", "only", "defer", "first", "last",
        "in_bulk", "iterator", "latest", "earliest",
    }

    _RAW_PATTERNS: List[re.Pattern] = [
        re.compile(r"\.raw\(|\.extra\("),
        re.compile(r"execute\(|cursor\(|text\("),
        re.compile(r"connection\.execute|db\.execute"),
    ]

    def build(self, graph: SemanticGraph, context: Dict[str, Any]) -> SemanticGraph:
        tree: Optional[ast.Module] = context.get("tree")
        file_path: str = context.get("file_path", "")

        if tree is None:
            return graph

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._extract_queries(node, graph, file_path)

        return graph

    def _extract_queries(
        self,
        func_node: ast.FunctionDef | ast.AsyncFunctionDef,
        graph: SemanticGraph,
        file_path: str,
    ) -> None:
        caller = G.ensure_function(graph, func_node.name, file_path)

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

        # Handle chained calls like Model.objects.filter(...)
        if isinstance(func, ast.Attribute):
            method_name = func.attr

            if method_name in self._QUERY_METHODS:
                model_name = self._extract_model_name(func.value)
                query_name = f"{model_name}.{method_name}" if model_name else method_name

                # Extract filter arguments
                filters: List[str] = []
                for kw in call.keywords:
                    if kw.arg:
                        filters.append(kw.arg)
                for arg in call.args:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        filters.append(arg.value)

                query = G.ensure_query(
                    graph, query_name, file_path,
                    operation=method_name,
                    target_model=model_name or "",
                    filters=filters,
                )
                graph.add_edge(UsesEdge(source=caller, target=query))

            # Raw SQL patterns
            for pattern in self._RAW_PATTERNS:
                if pattern.search(ast.unparse(func)):
                    query = G.ensure_query(
                        graph, "raw_sql", file_path,
                        operation="raw",
                    )
                    graph.add_edge(UsesEdge(source=caller, target=query))
                    break

    def _extract_model_name(self, node: ast.expr) -> Optional[str]:
        """Extract model name from chained attribute access."""
        if isinstance(node, ast.Attribute):
            if node.attr == "objects":
                if isinstance(node.value, ast.Name):
                    return node.value.id
            return self._extract_model_name(node.value)
        if isinstance(node, ast.Name):
            return node.id
        return None
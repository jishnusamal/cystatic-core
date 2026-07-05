"""Normalization parser — detects data normalization operations.

Detects:
    lower(), upper(), strip(), casefold(), normalize(), slugify(),
    uuid(), hash(), email canonicalization, trim, replace, split,
    join, timezone conversion
"""

from __future__ import annotations

import ast
from typing import Any, Dict, List, Optional, Set

from language_adapters.ir import (
    SemanticGraph,
    NodeType,
    FunctionNode,
    NormalizesEdge,
)
from language_adapters.interfaces.graph import GraphBuilder
from language_adapters.shared.graph_builder import GraphBuilderUtils as G


class NormalizationParser(GraphBuilder):
    """Extracts data normalization operations from function bodies."""

    _NORMALIZATION_METHODS: Dict[str, str] = {
        "lower": "lower",
        "upper": "upper",
        "strip": "strip",
        "lstrip": "strip",
        "rstrip": "strip",
        "casefold": "casefold",
        "normalize": "normalize",
        "slugify": "slugify",
        "replace": "replace",
        "split": "split",
        "join": "join",
        "trim": "trim",
    }

    _NORMALIZATION_FUNCS: Dict[str, str] = {
        "uuid": "uuid",
        "uuid4": "uuid",
        "uuid7": "uuid",
        "hash": "hash",
        "md5": "hash",
        "sha1": "hash",
        "sha256": "hash",
        "slugify": "slugify",
    }

    def build(self, graph: SemanticGraph, context: Dict[str, Any]) -> SemanticGraph:
        tree: Optional[ast.Module] = context.get("tree")
        file_path: str = context.get("file_path", "")

        if tree is None:
            return graph

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._extract_normalizations(node, graph, file_path)

        return graph

    def _extract_normalizations(
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

        # Method calls: str.lower(), email.strip()
        if isinstance(func, ast.Attribute):
            method = func.attr
            if method in self._NORMALIZATION_METHODS:
                norm_type = self._NORMALIZATION_METHODS[method]
                norm_node = FunctionNode(
                    name=method,
                    file_path=file_path,
                )
                graph.add_node(norm_node)
                graph.add_edge(
                    NormalizesEdge(
                        source=caller,
                        target=norm_node,
                        normalization_type=norm_type,
                    )
                )

        # Function calls: uuid4(), slugify()
        elif isinstance(func, ast.Name):
            name = func.id
            if name in self._NORMALIZATION_FUNCS:
                norm_type = self._NORMALIZATION_FUNCS[name]
                norm_node = FunctionNode(
                    name=name,
                    file_path=file_path,
                )
                graph.add_node(norm_node)
                graph.add_edge(
                    NormalizesEdge(
                        source=caller,
                        target=norm_node,
                        normalization_type=norm_type,
                    )
                )
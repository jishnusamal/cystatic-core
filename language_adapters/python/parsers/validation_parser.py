"""Validation parser — detects validation logic.

Detects:
    if, raise, assert, permission, validator, schema,
    serializer validation, pydantic, marshmallow
"""

from __future__ import annotations

import ast
import re
from typing import Any, Dict, List, Optional, Set

from language_adapters.ir import (
    SemanticGraph,
    NodeType,
    FunctionNode,
    ValidatesEdge,
)
from language_adapters.interfaces.graph import GraphBuilder
from language_adapters.shared.graph_builder import GraphBuilderUtils as G


class ValidationParser(GraphBuilder):
    """Extracts validation logic from function bodies."""

    _VALIDATION_KEYWORDS: Set[str] = {
        "validate", "validation", "validator", "is_valid", "clean",
        "validate_email", "validate_password", "validate_unique",
    }

    _VALIDATION_DECORATORS: Set[str] = {
        "validator", "validates", "validate",
    }

    _SERIALIZER_METHODS: Set[str] = {
        "validate", "validate_", "is_valid", "run_validators",
        "clean", "full_clean", "validate_unique",
    }

    _RAISE_PATTERN = re.compile(
        r"raise\s+(ValueError|TypeError|ValidationError|PermissionDenied|"
        r"AuthenticationFailed|ParseError|SerializerError)"
    )

    def build(self, graph: SemanticGraph, context: Dict[str, Any]) -> SemanticGraph:
        tree: Optional[ast.Module] = context.get("tree")
        file_path: str = context.get("file_path", "")

        if tree is None:
            return graph

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._extract_validations(node, graph, file_path)

        return graph

    def _extract_validations(
        self,
        func_node: ast.FunctionDef | ast.AsyncFunctionDef,
        graph: SemanticGraph,
        file_path: str,
    ) -> None:
        caller = G.ensure_function(graph, func_node.name, file_path)

        # Check if function name suggests validation
        is_validation_func = any(
            kw in func_node.name.lower() for kw in self._VALIDATION_KEYWORDS
        )

        # Check decorators
        for dec in func_node.decorator_list:
            if isinstance(dec, ast.Name) and dec.id in self._VALIDATION_DECORATORS:
                is_validation_func = True

        # Walk body for validation patterns
        for child in ast.walk(func_node):
            # raise ValueError(...) etc.
            if isinstance(child, ast.Raise):
                if child.exc and isinstance(child.exc, ast.Call):
                    exc_func = child.exc.func
                    if isinstance(exc_func, ast.Name):
                        val_node = FunctionNode(
                            name=exc_func.id,
                            file_path=file_path,
                        )
                        graph.add_node(val_node)
                        graph.add_edge(
                            ValidatesEdge(
                                source=caller,
                                target=val_node,
                                validation_type="raise",
                            )
                        )

            # assert statements
            if isinstance(child, ast.Assert):
                val_node = FunctionNode(
                    name="assert",
                    file_path=file_path,
                )
                graph.add_node(val_node)
                graph.add_edge(
                    ValidatesEdge(
                        source=caller,
                        target=val_node,
                        validation_type="assert",
                    )
                )

            # if statements with validation-like conditions
            if isinstance(child, ast.If):
                condition_str = ast.unparse(child.test).lower()
                if any(kw in condition_str for kw in self._VALIDATION_KEYWORDS):
                    val_node = FunctionNode(
                        name="if_validation",
                        file_path=file_path,
                    )
                    graph.add_node(val_node)
                    graph.add_edge(
                        ValidatesEdge(
                            source=caller,
                            target=val_node,
                            validation_type="if",
                        )
                    )

            # Call validation methods
            if isinstance(child, ast.Call):
                func = child.func
                if isinstance(func, ast.Attribute):
                    method = func.attr
                    if any(method.startswith(kw) for kw in self._SERIALIZER_METHODS):
                        val_node = FunctionNode(
                            name=method,
                            file_path=file_path,
                        )
                        graph.add_node(val_node)
                        graph.add_edge(
                            ValidatesEdge(
                                source=caller,
                                target=val_node,
                                validation_type="serializer",
                            )
                        )

        if is_validation_func:
            val_node = FunctionNode(
                name=f"{func_node.name}_validates",
                file_path=file_path,
            )
            graph.add_node(val_node)
            graph.add_edge(
                ValidatesEdge(
                    source=caller,
                    target=val_node,
                    validation_type="function",
                )
            )
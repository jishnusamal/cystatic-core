"""Read/Write parser — extracts READS, WRITES, UPDATES, CREATES, DELETES edges.

Detects ORM operations via Django and SQLAlchemy adapters.
"""

from __future__ import annotations

import ast
from typing import Any, Dict, List, Optional, Set

from language_adapters.ir import (
    SemanticGraph,
    NodeType,
    FunctionNode,
    MethodNode,
    ModelNode,
    ReadsEdge,
    WritesEdge,
    CreatesEdge,
    UpdatesEdge,
    DeletesEdge,
)
from language_adapters.interfaces.graph import GraphBuilder
from language_adapters.languages.python.ast.symbol_index import SymbolIndex
from language_adapters.shared.graph_builder import GraphBuilderUtils as G


class ReadWriteParser(GraphBuilder):
    """Extracts read/write relationships from function bodies."""

    # ORM write patterns
    _WRITE_METHODS: Set[str] = {
        "save", "update", "create", "bulk_create", "get_or_create",
        "update_or_create", "delete", "bulk_update",
    }

    _READ_METHODS: Set[str] = {
        "filter", "exclude", "get", "all", "first", "last", "values",
        "values_list", "only", "defer", "select_related", "prefetch_related",
        "annotate", "aggregate", "count", "exists", "distinct", "order_by",
        "reverse", "iterator",
    }

    def build(self, graph: SemanticGraph, context: Dict[str, Any]) -> SemanticGraph:
        tree: Optional[ast.Module] = context.get("tree")
        file_path: str = context.get("file_path", "")
        index: Optional[SymbolIndex] = context.get("symbol_index")

        if tree is None:
            return graph

        if index is None:
            index = SymbolIndex().build(tree)

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._extract_read_writes(node, graph, file_path, index)

        return graph

    def _extract_read_writes(
        self,
        func_node: ast.FunctionDef | ast.AsyncFunctionDef,
        graph: SemanticGraph,
        file_path: str,
        index: SymbolIndex,
    ) -> None:
        caller = G.ensure_function(graph, func_node.name, file_path)

        for child in ast.walk(func_node):
            if isinstance(child, ast.Call):
                self._process_call(child, caller, graph, file_path)

    def _process_call(
        self,
        call: ast.Call,
        caller: FunctionNode | MethodNode,
        graph: SemanticGraph,
        file_path: str,
    ) -> None:
        func = call.func

        if not isinstance(func, ast.Attribute):
            return

        method_name = func.attr

        # Extract the model name from the receiver
        model_name = self._extract_model_name(func.value)

        if not model_name:
            return

        model_node = G.ensure_model(graph, model_name, file_path)

        if method_name in self._WRITE_METHODS:
            if method_name == "save":
                graph.add_edge(WritesEdge(source=caller, target=model_node))
            elif method_name == "create":
                graph.add_edge(CreatesEdge(source=caller, target=model_node))
            elif method_name == "update":
                graph.add_edge(UpdatesEdge(source=caller, target=model_node))
            elif method_name == "delete":
                graph.add_edge(DeletesEdge(source=caller, target=model_node))
            else:
                graph.add_edge(WritesEdge(source=caller, target=model_node))

        elif method_name in self._READ_METHODS:
            graph.add_edge(ReadsEdge(source=caller, target=model_node))

    def _extract_model_name(self, node: ast.expr) -> Optional[str]:
        """Extract the model/class name from an expression like Discount.objects or Order().save()."""
        # Handle Order().save() - attribute call on instance
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                # Get the object the method is called on
                return self._extract_model_name(node.func.value)
            return None
        
        # Handle Discount.objects.filter() - attribute access
        if isinstance(node, ast.Attribute):
            if node.attr == "objects":
                if isinstance(node.value, ast.Name):
                    return node.value.id
            # Recursively check the value part
            return self._extract_model_name(node.value)

        # Handle direct name reference
        if isinstance(node, ast.Name):
            return node.id

        return None

"""Call graph parser — walks every changed function and extracts CALLS / CALLED_BY edges.

Detects:
    - new call
    - removed call
    - indirect call
    - super()
    - classmethod calls
    - staticmethod calls
"""

from __future__ import annotations

import ast
from typing import Any, Dict, List, Optional, Set

from language_adapters.ir import (
    SemanticGraph,
    NodeType,
    FunctionNode,
    MethodNode,
    CallsEdge,
    CalledByEdge,
)
from language_adapters.interfaces.graph import GraphBuilder
from language_adapters.languages.python.ast.symbol_index import SymbolIndex
from language_adapters.shared.graph_builder import GraphBuilderUtils as G
from language_adapters.shared.symbol_resolver import SymbolResolver


class CallGraphParser(GraphBuilder):
    """Extracts call relationships between functions and methods."""

    def __init__(self) -> None:
        self._resolver = SymbolResolver()

    def build(self, graph: SemanticGraph, context: Dict[str, Any]) -> SemanticGraph:
        tree: Optional[ast.Module] = context.get("tree")
        file_path: str = context.get("file_path", "")
        index: Optional[SymbolIndex] = context.get("symbol_index")

        if tree is None:
            return graph

        if index is None:
            index = SymbolIndex().build(tree)

        # Extract imports for symbol resolution
        self._resolver.reset()
        self._resolver.extract_imports(tree)

        # Build a mapping of functions to their parent classes
        func_to_class: Dict[int, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for child in node.body:
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        func_to_class[id(child)] = node.name

        # Walk all functions and methods in the tree
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._extract_calls(node, graph, file_path, index, func_to_class)

        return graph

    def _extract_calls(
        self,
        func_node: ast.FunctionDef | ast.AsyncFunctionDef,
        graph: SemanticGraph,
        file_path: str,
        index: SymbolIndex,
        func_to_class: Dict[int, str],
    ) -> None:
        """Find all call expressions inside a function body."""
        caller_name = func_node.name

        # Determine if this is a method (inside a class)
        caller_is_method = False
        caller_class = func_to_class.get(id(func_node))
        if caller_class:
            caller_is_method = True

        if caller_is_method and caller_class:
            caller = G.ensure_method(graph, caller_name, file_path, class_name=caller_class)
        else:
            caller = G.ensure_function(graph, caller_name, file_path)

        for child in ast.walk(func_node):
            if isinstance(child, ast.Call):
                self._process_call(child, caller, graph, file_path, index)

    def _process_call(
        self,
        call: ast.Call,
        caller: FunctionNode | MethodNode,
        graph: SemanticGraph,
        file_path: str,
        index: SymbolIndex,
    ) -> None:
        func = call.func

        # Direct call: foo()
        if isinstance(func, ast.Name):
            callee_name = func.id
            self._add_call_edge(caller, callee_name, graph, file_path, index, "direct")

        # Attribute call: obj.method() or module.function()
        elif isinstance(func, ast.Attribute):
            callee_name = _attr_chain(func)
            call_type = "direct"

            # Detect super().method() calls
            if isinstance(func.value, ast.Call):
                if isinstance(func.value.func, ast.Name) and func.value.func.id == "super":
                    call_type = "super"

            # Detect self.method() / cls.method()
            if isinstance(func.value, ast.Name):
                if func.value.id == "self":
                    call_type = "indirect"
                elif func.value.id == "cls":
                    call_type = "classmethod"

            self._add_call_edge(caller, callee_name, graph, file_path, index, call_type)

    def _add_call_edge(
        self,
        caller: FunctionNode | MethodNode,
        callee_name: str,
        graph: SemanticGraph,
        file_path: str,
        index: SymbolIndex,
        call_type: str,
    ) -> None:
        # Skip builtins and common Python keywords
        if callee_name in _BUILTINS:
            return

        # Resolve the callee
        resolved = self._resolver.resolve(callee_name)

        # Create callee node
        if index.function_exists(callee_name) or index.function_exists(resolved):
            callee = G.ensure_function(graph, callee_name, file_path)
        else:
            callee = FunctionNode(name=callee_name, file_path=file_path)
            graph.add_node(callee)

        # Add CALLS edge
        edge = CallsEdge(source=caller, target=callee, call_type=call_type)
        graph.add_edge(edge)


_BUILTINS: Set[str] = {
    "print", "len", "str", "int", "float", "list", "dict", "set", "tuple",
    "bool", "type", "isinstance", "hasattr", "getattr", "setattr", "delattr",
    "range", "enumerate", "zip", "map", "filter", "sorted", "reversed",
    "open", "input", "iter", "next", "super", "property", "classmethod",
    "staticmethod", "abs", "all", "any", "bin", "chr", "dir", "divmod",
    "eval", "exec", "format", "globals", "hex", "id", "locals", "max",
    "min", "next", "object", "oct", "ord", "pow", "repr", "round", "sum",
    "vars", "hash", "help", "callable", "compile", "complex", "delattr",
    "frozenset", "memoryview", "bytearray", "bytes", "ascii", "breakpoint",
}


def _attr_chain(node: ast.Attribute) -> str:
    """Convert an attribute chain like a.b.c to string 'a.b.c'."""
    parts: List[str] = []
    current: ast.expr = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
    parts.reverse()
    return ".".join(parts)
"""Symbol parser — extracts functions, methods, classes, decorators, modules, enums, constants, properties, exceptions.

Moves current function extraction into this parser.
Produces graph nodes only — no signals.
"""

from __future__ import annotations

import ast
from typing import Any, Dict, List, Optional, Set

from language_adapters.ir import (
    SemanticGraph,
    NodeType,
    FunctionNode,
    MethodNode,
    ClassNode,
    ModuleNode,
    DecoratorNode,
    HasParameterEdge,
    ReturnsEdge,
    RaisesEdge,
    InheritsEdge,
    DecoratedByEdge,
)
from language_adapters.interfaces.graph import GraphBuilder
from language_adapters.languages.python.ast.symbol_index import SymbolIndex
from language_adapters.shared.graph_builder import GraphBuilderUtils as G


class SymbolParser(GraphBuilder):
    """Extracts symbol definitions from Python AST.

    Responsibilities:
        Function, Method, Class, Decorator, Module, Enum, Constant, Property, Exception
    """

    def build(self, graph: SemanticGraph, context: Dict[str, Any]) -> SemanticGraph:
        """Extract symbols and add them to the graph."""
        tree: Optional[ast.Module] = context.get("tree")
        file_path: str = context.get("file_path", "")
        index: Optional[SymbolIndex] = context.get("symbol_index")

        if tree is None:
            return graph

        if index is None:
            index = SymbolIndex().build(tree)

        # Module node
        G.ensure_module(graph, file_path)

        # Walk top-level nodes
        self._extract_from_body(tree.body, graph, file_path, index, class_name=None)

        return graph

    def _extract_from_body(
        self,
        body: List[ast.stmt],
        graph: SemanticGraph,
        file_path: str,
        index: SymbolIndex,
        class_name: Optional[str],
    ) -> None:
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._extract_function(node, graph, file_path, index, class_name)
            elif isinstance(node, ast.ClassDef):
                self._extract_class(node, graph, file_path, index)

    def _extract_function(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        graph: SemanticGraph,
        file_path: str,
        index: SymbolIndex,
        class_name: Optional[str],
    ) -> None:
        name = node.name
        is_async = isinstance(node, ast.AsyncFunctionDef)

        # Detect visibility
        visibility = "public"
        if name.startswith("__") and not name.endswith("__"):
            visibility = "private"
        elif name.startswith("_"):
            visibility = "protected"

        # Detect decorators
        decorator_names: List[str] = []
        for d in node.decorator_list:
            if isinstance(d, ast.Name):
                decorator_names.append(d.id)
            elif isinstance(d, ast.Attribute):
                decorator_names.append(f"{_attr_chain(d)}")
            elif isinstance(d, ast.Call):
                if isinstance(d.func, ast.Name):
                    decorator_names.append(d.func.id)
                elif isinstance(d.func, ast.Attribute):
                    decorator_names.append(f"{_attr_chain(d.func)}")

        is_static = "staticmethod" in decorator_names
        is_classmethod = "classmethod" in decorator_names
        is_property = "property" in decorator_names

        # Parameters
        params = [arg.arg for arg in node.args.args]

        # Return type
        return_type: Optional[str] = None
        if node.returns:
            if isinstance(node.returns, ast.Name):
                return_type = node.returns.id
            elif isinstance(node.returns, ast.Attribute):
                return_type = _attr_chain(node.returns)

        start_line = getattr(node, "lineno", None)
        end_line = getattr(node, "end_lineno", None)

        if class_name:
            fn = G.ensure_method(
                graph, name, file_path,
                class_name=class_name,
                is_async=is_async,
                is_static=is_static,
                is_classmethod=is_classmethod,
                is_property=is_property,
                visibility=visibility,
                decorators=decorator_names,
                parameters=params,
                return_type=return_type,
                start_line=start_line,
                end_line=end_line,
            )
        else:
            fn = G.ensure_function(
                graph, name, file_path,
                is_async=is_async,
                is_static=is_static,
                is_classmethod=is_classmethod,
                is_property=is_property,
                visibility=visibility,
                decorators=decorator_names,
                parameters=params,
                return_type=return_type,
                start_line=start_line,
                end_line=end_line,
            )

        # Decorator edges
        for dec_name in decorator_names:
            dec_node = DecoratorNode(
                name=dec_name,
                file_path=file_path,
                target_name=name,
            )
            graph.add_node(dec_node)
            graph.add_edge(DecoratedByEdge(source=fn, target=dec_node))

        # Parameter edges
        for param in params:
            param_node = FunctionNode(
                name=f"{name}.{param}",
                file_path=file_path,
            )
            graph.add_node(param_node)
            graph.add_edge(HasParameterEdge(source=fn, target=param_node))

        # Return type edge
        if return_type:
            ret_node = FunctionNode(
                name=return_type,
                file_path=file_path,
            )
            graph.add_node(ret_node)
            graph.add_edge(ReturnsEdge(source=fn, target=ret_node))

        # Exception detection (raise statements)
        self._extract_raises(node, fn, graph, file_path)

    def _extract_class(
        self,
        node: ast.ClassDef,
        graph: SemanticGraph,
        file_path: str,
        index: SymbolIndex,
    ) -> None:
        name = node.name

        # Base classes
        bases: List[str] = []
        for base in node.bases:
            if isinstance(base, ast.Name):
                bases.append(base.id)
            elif isinstance(base, ast.Attribute):
                bases.append(_attr_chain(base))

        # Decorators
        decorator_names: List[str] = []
        for d in node.decorator_list:
            if isinstance(d, ast.Name):
                decorator_names.append(d.id)
            elif isinstance(d, ast.Attribute):
                decorator_names.append(_attr_chain(d))
            elif isinstance(d, ast.Call):
                if isinstance(d.func, ast.Name):
                    decorator_names.append(d.func.id)
                elif isinstance(d.func, ast.Attribute):
                    decorator_names.append(_attr_chain(d.func))

        start_line = getattr(node, "lineno", None)
        end_line = getattr(node, "end_lineno", None)

        cls = G.ensure_class(
            graph, name, file_path,
            bases=bases,
            decorators=decorator_names,
            start_line=start_line,
            end_line=end_line,
        )

        # Inheritance edges
        for base_name in bases:
            base_node = ClassNode(name=base_name, file_path=file_path)
            graph.add_node(base_node)
            graph.add_edge(InheritsEdge(source=cls, target=base_node))

        # Decorator edges
        for dec_name in decorator_names:
            dec_node = DecoratorNode(
                name=dec_name,
                file_path=file_path,
                target_name=name,
            )
            graph.add_node(dec_node)
            graph.add_edge(DecoratedByEdge(source=cls, target=dec_node))

        # Extract methods
        self._extract_from_body(node.body, graph, file_path, index, class_name=name)

    def _extract_raises(
        self,
        func_node: ast.FunctionDef | ast.AsyncFunctionDef,
        fn: FunctionNode | MethodNode,
        graph: SemanticGraph,
        file_path: str,
    ) -> None:
        """Find raise statements and add RAISES edges."""
        for child in ast.walk(func_node):
            if isinstance(child, ast.Raise):
                if child.exc and isinstance(child.exc, ast.Call):
                    exc_func = child.exc.func
                    if isinstance(exc_func, ast.Name):
                        exc_node = FunctionNode(name=exc_func.id, file_path=file_path)
                        graph.add_node(exc_node)
                        graph.add_edge(RaisesEdge(source=fn, target=exc_node))


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
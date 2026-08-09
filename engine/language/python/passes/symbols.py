"""Python symbol index pass - extracts symbols from Python AST.

Only emits structural facts: function/class/method names, lines, visibility.
No semantic inference, no reference resolution.
"""

import ast
from typing import Any

from language_adapters.base.file_context import FileContext
from language_adapters.base.passes import BaseIndexPass
from engine.repository.model.repository_index import SymbolEntry


def _determine_visibility(name: str) -> str:
    """Determine visibility from naming convention."""
    if name.startswith('__') and name.endswith('__'):
        return 'public'
    elif name.startswith('_'):
        return 'private'
    return 'public'


def _get_decorator_names(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    """Get decorator names from a function."""
    decorators = []
    for dec in node.decorator_list:
        if isinstance(dec, ast.Attribute):
            if isinstance(dec.value, ast.Name):
                decorators.append(f"{dec.value.id}.{dec.attr}")
        elif isinstance(dec, ast.Name):
            decorators.append(dec.id)
    return decorators


def _get_base_names(node: ast.ClassDef) -> list[str]:
    """Get base class names from a class definition."""
    bases = []
    for base in node.bases:
        if isinstance(base, ast.Name):
            bases.append(base.id)
    return bases


class PythonSymbolIndexPass(BaseIndexPass):
    """Index pass that extracts symbol facts from Python AST.

    Extracts: functions, classes, methods with their names, lines, visibility.
    No semantic interpretation - just structural symbol discovery.

    Supports both the visitor pattern (visit_FunctionDef, visit_ClassDef)
    and the traditional process() method for backward compatibility.
    """

    def process(self, context: FileContext, builder: dict[str, Any]) -> None:
        """Extract symbols from a Python file context (legacy mode)."""
        tree = context.ast
        file_path = context.path

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                builder["symbols"].append(self._extract_function(node, file_path))
            elif isinstance(node, ast.ClassDef):
                class_sym, method_syms = self._extract_class(node, file_path)
                builder["symbols"].append(class_sym)
                builder["symbols"].extend(method_syms)

    def visit_FunctionDef(self, node: ast.FunctionDef | ast.AsyncFunctionDef, context: FileContext, builder: dict[str, Any]) -> None:
        """Handle function definition node from visitor."""
        builder["symbols"].append(self._extract_function(node, context.path))

    def visit_ClassDef(self, node: ast.ClassDef, context: FileContext, builder: dict[str, Any]) -> None:
        """Handle class definition node from visitor."""
        class_sym, method_syms = self._extract_class(node, context.path)
        builder["symbols"].append(class_sym)
        builder["symbols"].extend(method_syms)

    def _extract_function(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        file_path: str,
    ) -> SymbolEntry:
        """Extract a function definition symbol."""
        properties: dict[str, Any] = {
            "decorators": _get_decorator_names(node),
        }

        docstring = ast.get_docstring(node)
        if docstring:
            properties["docstring"] = docstring

        return SymbolEntry(
            name=node.name,
            kind="function",
            file=file_path,
            start_line=node.lineno,
            end_line=node.end_lineno or node.lineno,
            visibility=_determine_visibility(node.name),
            properties=properties,
        )

    def _extract_class(
        self,
        node: ast.ClassDef,
        file_path: str,
    ) -> tuple[SymbolEntry, list[SymbolEntry]]:
        """Extract a class definition with its methods.

        Returns:
            Tuple of (class_symbol, list_of_method_symbols)
        """
        properties: dict[str, Any] = {
            "bases": _get_base_names(node),
        }

        docstring = ast.get_docstring(node)
        if docstring:
            properties["docstring"] = docstring

        method_symbols: list[SymbolEntry] = []
        for child in node.body:
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                method_props: dict[str, Any] = {}
                method_doc = ast.get_docstring(child)
                if method_doc:
                    method_props["docstring"] = method_doc

                method_sym = SymbolEntry(
                    name=child.name,
                    kind="method",
                    file=file_path,
                    start_line=child.lineno,
                    end_line=child.end_lineno or child.lineno,
                    visibility=_determine_visibility(child.name),
                    parent=node.name,
                    properties=method_props,
                )
                method_symbols.append(method_sym)

        class_sym = SymbolEntry(
            name=node.name,
            kind="class",
            file=file_path,
            start_line=node.lineno,
            end_line=node.end_lineno or node.lineno,
            visibility=_determine_visibility(node.name),
            properties=properties,
        )
        return class_sym, method_symbols

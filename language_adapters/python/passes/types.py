"""Python type index pass - extracts type relationships from Python AST.

Emits only raw type relationship facts. No resolution, no symbol matching.
"""

import ast
from typing import Any

from language_adapters.base.file_context import FileContext
from language_adapters.base.passes import BaseIndexPass
from language_adapters.model.repository_index import TypeRelationshipEntry


class PythonTypeIndexPass(BaseIndexPass):
    """Index pass that extracts type relationship facts from Python AST.

    Extracts inheritance, composition, and other type relationships.
    No resolution — relationships are stored with raw names.

    Supports both the visitor pattern (visit_ClassDef) and the traditional
    process() method for backward compatibility.
    """

    def process(self, context: FileContext, builder: dict[str, Any]) -> None:
        """Extract type relationships from a Python file context (legacy mode)."""
        tree = context.ast
        file_path = context.path

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.ClassDef):
                self._extract_type_relationships(node, file_path, builder)

    def visit_ClassDef(self, node: ast.ClassDef, context: FileContext, builder: dict[str, Any]) -> None:
        """Handle class definition node from visitor."""
        self._extract_type_relationships(node, context.path, builder)

    def _extract_type_relationships(self, node: ast.ClassDef, file_path: str, builder: dict[str, Any]) -> None:
        """Extract type relationships from a class definition."""
        for base in node.bases:
            base_str = self._base_to_string(base)
            if base_str:
                builder["type_relationships"].append(
                    TypeRelationshipEntry(
                        source=node.name,
                        target=base_str,
                        relation_type="extends",
                        file=file_path,
                        line=node.lineno,
                    )
                )

    def _base_to_string(self, node: ast.AST) -> str:
        """Convert a base class node to a string representation."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            parts = []
            current = node
            while isinstance(current, ast.Attribute):
                parts.append(current.attr)
                current = current.value
            if isinstance(current, ast.Name):
                parts.append(current.id)
            return ".".join(reversed(parts))
        return ""
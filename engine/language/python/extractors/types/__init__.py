"""Python type relationship extractor - extracts inheritance, composition, and generic relationships."""

import ast
from typing import Any

from engine.language.base import BaseExtractor


class PythonTypeExtractor(BaseExtractor):
    """
    Extracts type relationships from Python source files.

    Discovers:
    - Class inheritance (extends)
    - ABC/implements relationships
    - Composition relationships (type hints on fields)
    - Generic type references

    Produces a list of dicts with keys: source_sym, target_sym, relation_type, metadata.
    """

    def extract(self, tree: ast.AST, file_path: str) -> list[dict[str, Any]]:
        """
        Extract all type relationships from a Python AST.

        Args:
            tree: Parsed Python AST
            file_path: Path to the source file

        Returns:
            List of relationship dicts with source, target, relation_type, metadata
        """
        relationships = []

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.ClassDef):
                # Inheritance relationships
                for base in node.bases:
                    target = self._resolve_base_name(base)
                    if target:
                        relationships.append({
                            'source_sym': f"python://{file_path}#{node.name}",
                            'target_sym': target,
                            'relation_type': 'extends',
                            'metadata': {'file': file_path, 'line': node.lineno},
                        })

                # Composition relationships from type-annotated fields
                for child in node.body:
                    if isinstance(child, ast.AnnAssign) and isinstance(child.target, ast.Name):
                        field_name = child.target.id
                        type_hint = self._resolve_type_hint(child.annotation)
                        if type_hint:
                            relationships.append({
                                'source_sym': f"python://{file_path}#{node.name}",
                                'target_sym': type_hint,
                                'relation_type': 'composes',
                                'metadata': {
                                    'field': field_name,
                                    'file': file_path,
                                    'line': child.lineno,
                                },
                            })

        return relationships

    def _resolve_base_name(self, node: ast.AST) -> str | None:
        """Resolve a base class node to a symbol reference string."""
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
            return '.'.join(reversed(parts))
        elif isinstance(node, ast.Subscript):
            return self._resolve_base_name(node.value)
        return None

    def _resolve_type_hint(self, node: ast.AST | None) -> str | None:
        """Resolve a type annotation to a symbol reference string."""
        if node is None:
            return None
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
            return '.'.join(reversed(parts))
        elif isinstance(node, ast.Subscript):
            # Generic type like List[str], Optional[User]
            base = self._resolve_type_hint(node.value)
            arg = self._resolve_type_hint(node.slice)
            if base and arg:
                return f"{base}[{arg}]"
            return base
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            # Forward reference string annotation
            return node.value
        return None
"""AST loader for Python files.

Loads AST from file content, handling syntax errors gracefully.
"""

from __future__ import annotations

import ast
from typing import Optional


class ASTLoader:
    """Loads Python AST from file content."""

    @staticmethod
    def load(content: str) -> Optional[ast.Module]:
        """Parse Python source code into an AST.

        Args:
            content: Python source code.

        Returns:
            Parsed AST module, or None if syntax error.
        """
        try:
            return ast.parse(content)
        except SyntaxError:
            return None

    @staticmethod
    def load_from_file(file_path: str) -> Optional[ast.Module]:
        """Read and parse a Python file.

        Args:
            file_path: Path to the Python file.

        Returns:
            Parsed AST module, or None if syntax error or file not found.
        """
        try:
            with open(file_path) as f:
                return ast.parse(f.read())
        except (SyntaxError, FileNotFoundError, IOError):
            return None

    @staticmethod
    def get_changed_ranges(
        tree: ast.Module,
        changed_lines: set[int],
    ) -> list[ast.AST]:
        """Get the AST nodes that contain changed lines.

        Args:
            tree: The full AST.
            changed_lines: Set of line numbers that changed.

        Returns:
            List of top-level AST nodes that contain any changed lines.
        """
        changed_nodes: list[ast.AST] = []
        for node in ast.iter_child_nodes(tree):
            start = getattr(node, "lineno", 0)
            end = getattr(node, "end_lineno", start)
            if any(start <= line <= end for line in changed_lines):
                changed_nodes.append(node)
        return changed_nodes
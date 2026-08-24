"""Python parser - wraps Python's built-in ast module as a BaseParser."""

import ast

from engine.language.base.parser import BaseParser


class PythonParser(BaseParser):
    """
    Python source code parser using the built-in `ast` module.

    Wraps ast.parse() to conform to the BaseParser interface,
    allowing the Python adapter to use this through the parser abstraction.
    """

    def parse(self, content: str, file_path: str) -> ast.AST:
        """
        Parse a Python source file into an AST.

        Args:
            content: Raw Python source code
            file_path: Path to the source file (used for error messages)

        Returns:
            Python AST (ast.Module)

        Raises:
            SyntaxError: If the source contains syntax errors
        """
        return ast.parse(content, filename=file_path)

    def supports_file(self, file_path: str) -> bool:
        """
        Check if this parser supports a given file.

        Args:
            file_path: Path to the source file

        Returns:
            True if the file ends with .py
        """
        return file_path.endswith(".py")

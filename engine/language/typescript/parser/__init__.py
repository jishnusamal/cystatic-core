"""TypeScript parser - wraps Tree-sitter TypeScript parser as a BaseParser."""

from typing import Any
from tree_sitter import Language, Parser
import tree_sitter_typescript as tstypescript

from engine.language.base.parser import BaseParser


class TypeScriptParser(BaseParser):
    """
    TypeScript and TSX source code parser using tree-sitter.
    """

    def __init__(self) -> None:
        """Initialize the Tree-sitter parsers."""
        self._ts_lang = Language(tstypescript.language_typescript())
        self._tsx_lang = Language(tstypescript.language_tsx())
        
        self._ts_parser = Parser(self._ts_lang)
        self._tsx_parser = Parser(self._tsx_lang)

    def parse(self, content: str, file_path: str) -> Any:
        """
        Parse a TypeScript/TSX source file into a tree-sitter Tree.

        Args:
            content: Raw source code string
            file_path: Path to the source file

        Returns:
            tree_sitter.Tree object
        """
        content_bytes = content.encode("utf-8")
        if file_path.endswith(".tsx"):
            return self._tsx_parser.parse(content_bytes)
        return self._ts_parser.parse(content_bytes)

    def supports_file(self, file_path: str) -> bool:
        """
        Check if this parser supports a given file.

        Args:
            file_path: Path to the source file

        Returns:
            True if the file ends with .ts, .tsx, .mts, or .cts
        """
        return file_path.endswith((".ts", ".tsx", ".mts", ".cts"))

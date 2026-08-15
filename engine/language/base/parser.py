"""Base parser abstraction - defines the contract for language-specific parsers."""

from abc import ABC, abstractmethod
from typing import Any


class BaseParser(ABC):
    """
    Abstract base class for all language parsers.

    The parser is responsible for converting source files into a language-native
    syntax tree representation. It exposes syntax only - no semantic interpretation.

    Each language adapter uses its own parser implementation.
    """

    @abstractmethod
    def parse(self, content: str, file_path: str) -> Any:
        """
        Parse a source file into a language-native syntax tree.

        Args:
            content: Raw source file content
            file_path: Path to the source file

        Returns:
            Language-native syntax tree representation

        Raises:
            SyntaxError: If the source file contains syntax errors
        """
        pass

    @abstractmethod
    def supports_file(self, file_path: str) -> bool:
        """
        Check if this parser supports a given file.

        Args:
            file_path: Path to the source file

        Returns:
            True if the file extension/language is supported
        """
        pass

"""Language plugin protocol definition."""

from typing import Protocol

from .adapter import BaseLanguageAdapter
from .spec import LanguageSpec


class LanguagePlugin(Protocol):
    """Protocol representing the registration/discovery boundary for a language implementation."""

    spec: LanguageSpec

    def create_adapter(self) -> BaseLanguageAdapter:
        """Create a new instance of the language adapter."""
        ...

"""Python language plugin implementation."""

from engine.language.base.adapter import BaseLanguageAdapter
from engine.language.base.spec import LanguageSpec

from .adapter import PythonLanguageAdapter


class PythonPlugin:
    """Concrete plugin implementation for Python."""

    spec = LanguageSpec(
        id="python",
        extensions=frozenset({".py"}),
    )

    def create_adapter(self) -> BaseLanguageAdapter:
        """Create a PythonLanguageAdapter instance."""
        return PythonLanguageAdapter()

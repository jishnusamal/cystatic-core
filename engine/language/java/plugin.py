"""Java language plugin implementation."""

from engine.language.base.adapter import BaseLanguageAdapter
from engine.language.base.spec import LanguageSpec

from .adapter import JavaLanguageAdapter


class JavaPlugin:
    """Concrete plugin implementation for Java."""

    spec = LanguageSpec(
        id="java",
        extensions=frozenset({".java"}),
    )

    def create_adapter(self) -> BaseLanguageAdapter:
        """Create a JavaLanguageAdapter instance."""
        return JavaLanguageAdapter()

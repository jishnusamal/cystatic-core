"""Java language plugin implementation."""

from engine.language.base.adapter import BaseLanguageAdapter
from engine.language.base.spec import LanguageSpec
from engine.language.base.capabilities import LanguageCapabilities

from .adapter import JavaLanguageAdapter


class JavaPlugin:
    """Concrete plugin implementation for Java."""

    spec = LanguageSpec(
        id="java",
        extensions=frozenset({".java"}),
        capabilities=LanguageCapabilities(
            symbols=True,
            imports=True,
            calls=True,
            types=True,
            entrypoints=True,
            events=True,
            persistence=True,
            tests=True,
        ),
    )

    def create_adapter(self) -> BaseLanguageAdapter:
        """Create a JavaLanguageAdapter instance."""
        return JavaLanguageAdapter()

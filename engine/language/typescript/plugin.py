"""TypeScript language plugin implementation."""

from engine.language.base.adapter import BaseLanguageAdapter
from engine.language.base.capabilities import LanguageCapabilities
from engine.language.base.spec import LanguageSpec


class TypeScriptPlugin:
    """Concrete plugin implementation for TypeScript."""

    spec = LanguageSpec(
        id="typescript",
        extensions=frozenset({".ts", ".tsx", ".mts", ".cts"}),
        capabilities=LanguageCapabilities(
            symbols=True,
            imports=True,
            calls=True,
            types=True,
            entrypoints=True,
            events=False,
            persistence=False,
            tests=False,
        ),
    )

    def create_adapter(self) -> BaseLanguageAdapter:
        """Create a TypeScriptLanguageAdapter instance."""
        from .adapter import TypeScriptLanguageAdapter
        return TypeScriptLanguageAdapter()

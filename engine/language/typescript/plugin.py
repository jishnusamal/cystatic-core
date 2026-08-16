"""TypeScript language plugin implementation."""

from engine.language.base.adapter import BaseLanguageAdapter
from engine.language.base.spec import LanguageSpec
from core.errors import LanguageNotSupported


class TypeScriptPlugin:
    """Concrete plugin implementation for TypeScript."""

    spec = LanguageSpec(
        id="typescript",
        extensions=frozenset({".ts", ".tsx"}),
    )

    def create_adapter(self) -> BaseLanguageAdapter:
        """Create a TypeScriptLanguageAdapter instance."""
        # Since TypeScript adapter is not implemented, raise LanguageNotSupported
        raise LanguageNotSupported(
            "TypeScript language adapter is not supported.",
            details={"language": "typescript"},
        )

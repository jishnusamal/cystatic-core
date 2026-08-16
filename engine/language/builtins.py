"""Built-in language plugin registry configuration."""

from engine.language.java.plugin import JavaPlugin
from engine.language.python.plugin import PythonPlugin
from engine.language.registry import LanguageRegistry
from engine.language.typescript.plugin import TypeScriptPlugin


def create_default_language_registry() -> LanguageRegistry:
    """Create a default language registry populated with built-in plugins."""
    registry = LanguageRegistry()

    registry.register(PythonPlugin())
    registry.register(TypeScriptPlugin())
    registry.register(JavaPlugin())

    return registry

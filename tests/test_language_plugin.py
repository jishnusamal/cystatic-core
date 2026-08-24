from engine.language.base import BaseLanguageAdapter, LanguagePlugin, LanguageSpec
from engine.language.java.adapter import JavaLanguageAdapter
from engine.language.java.plugin import JavaPlugin
from engine.language.python.adapter import PythonLanguageAdapter
from engine.language.python.plugin import PythonPlugin
from engine.language.typescript.adapter import TypeScriptLanguageAdapter
from engine.language.typescript.plugin import TypeScriptPlugin


def test_python_plugin_spec():
    """Verify PythonPlugin metadata."""
    plugin = PythonPlugin()

    assert plugin.spec.id == "python"
    assert plugin.spec.extensions == frozenset({".py"})
    assert isinstance(plugin.spec, LanguageSpec)


def test_python_plugin_creates_adapter():
    """Verify PythonPlugin adapter construction."""
    plugin = PythonPlugin()

    adapter = plugin.create_adapter()

    assert isinstance(adapter, PythonLanguageAdapter)
    assert isinstance(adapter, BaseLanguageAdapter)


def test_java_plugin_spec():
    """Verify JavaPlugin metadata."""
    plugin = JavaPlugin()

    assert plugin.spec.id == "java"
    assert plugin.spec.extensions == frozenset({".java"})
    assert isinstance(plugin.spec, LanguageSpec)


def test_java_plugin_creates_adapter():
    """Verify JavaPlugin adapter construction."""
    plugin = JavaPlugin()

    adapter = plugin.create_adapter()

    assert isinstance(adapter, JavaLanguageAdapter)
    assert isinstance(adapter, BaseLanguageAdapter)


def test_protocol_compatibility():
    """Static type assertion to ensure plugins satisfy LanguagePlugin protocol."""
    # These assignments will be validated by static type checkers (e.g. mypy)
    python_plugin: LanguagePlugin = PythonPlugin()
    java_plugin: LanguagePlugin = JavaPlugin()
    typescript_plugin: LanguagePlugin = TypeScriptPlugin()

    assert python_plugin.spec.id == "python"
    assert java_plugin.spec.id == "java"
    assert typescript_plugin.spec.id == "typescript"


def test_typescript_plugin_spec():
    """Verify TypeScriptPlugin metadata."""
    plugin = TypeScriptPlugin()

    assert plugin.spec.id == "typescript"
    assert plugin.spec.extensions == frozenset({".ts", ".tsx", ".mts", ".cts"})
    assert isinstance(plugin.spec, LanguageSpec)


def test_typescript_plugin_creates_adapter():
    """Verify TypeScriptPlugin adapter construction."""
    plugin = TypeScriptPlugin()
    adapter = plugin.create_adapter()

    assert isinstance(adapter, TypeScriptLanguageAdapter)
    assert isinstance(adapter, BaseLanguageAdapter)


def test_python_adapter_contract():
    """Verify that PythonLanguageAdapter implements BaseLanguageAdapter and exposes correct interface."""
    adapter = PythonLanguageAdapter()
    assert isinstance(adapter, BaseLanguageAdapter)
    assert hasattr(adapter, "compile")
    assert hasattr(adapter, "compile_incremental")
    assert hasattr(adapter, "get_language")
    assert hasattr(adapter, "get_compiler_passes")
    assert adapter.get_language() == "python"


def test_java_adapter_contract():
    """Verify that JavaLanguageAdapter implements BaseLanguageAdapter and exposes correct interface."""
    adapter = JavaLanguageAdapter()
    assert isinstance(adapter, BaseLanguageAdapter)
    assert hasattr(adapter, "compile")
    assert hasattr(adapter, "compile_incremental")
    assert hasattr(adapter, "get_language")
    assert hasattr(adapter, "get_compiler_passes")
    assert adapter.get_language() == "java"


def test_python_plugin_capabilities():
    """Verify PythonPlugin advertises supported capabilities."""
    plugin = PythonPlugin()
    assert plugin.spec.capabilities.symbols is True
    assert plugin.spec.capabilities.imports is True
    assert plugin.spec.capabilities.calls is True
    assert plugin.spec.capabilities.types is True
    assert plugin.spec.capabilities.entrypoints is True
    assert plugin.spec.capabilities.events is True
    assert plugin.spec.capabilities.persistence is True
    assert plugin.spec.capabilities.tests is True


def test_java_plugin_capabilities():
    """Verify JavaPlugin advertises supported capabilities."""
    plugin = JavaPlugin()
    assert plugin.spec.capabilities.symbols is True
    assert plugin.spec.capabilities.imports is True
    assert plugin.spec.capabilities.calls is True
    assert plugin.spec.capabilities.types is True
    assert plugin.spec.capabilities.entrypoints is True
    assert plugin.spec.capabilities.events is True
    assert plugin.spec.capabilities.persistence is True
    assert plugin.spec.capabilities.tests is True


def test_typescript_plugin_capabilities():
    """Verify TypeScriptPlugin advertises supported capabilities."""
    plugin = TypeScriptPlugin()
    assert plugin.spec.capabilities.symbols is True
    assert plugin.spec.capabilities.imports is True
    assert plugin.spec.capabilities.calls is True
    assert plugin.spec.capabilities.types is True
    assert plugin.spec.capabilities.entrypoints is True
    assert plugin.spec.capabilities.events is False
    assert plugin.spec.capabilities.persistence is False
    assert plugin.spec.capabilities.tests is False


def test_builtin_language_capabilities():
    """Verify default language capability matrix from default registry."""
    from engine.language.builtins import create_default_language_registry

    registry = create_default_language_registry()

    python = registry.get("python").spec
    java = registry.get("java").spec
    typescript = registry.get("typescript").spec

    assert python.capabilities.symbols is True
    assert python.capabilities.calls is True

    assert java.capabilities.symbols is True
    assert java.capabilities.calls is True

    assert typescript.capabilities.symbols is True
    assert typescript.capabilities.calls is True


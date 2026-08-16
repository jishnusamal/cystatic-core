from engine.language.base import LanguagePlugin, LanguageSpec, BaseLanguageAdapter
from engine.language.python.plugin import PythonPlugin
from engine.language.python.adapter import PythonLanguageAdapter
from engine.language.java.plugin import JavaPlugin
from engine.language.java.adapter import JavaLanguageAdapter
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
    assert plugin.spec.extensions == frozenset({".ts", ".tsx"})
    assert isinstance(plugin.spec, LanguageSpec)


def test_typescript_plugin_creates_adapter():
    """Verify TypeScriptPlugin adapter construction raises LanguageNotSupported."""
    import pytest
    from core.errors import LanguageNotSupported

    plugin = TypeScriptPlugin()

    with pytest.raises(LanguageNotSupported):
        plugin.create_adapter()


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


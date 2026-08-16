from engine.language.base import LanguagePlugin, LanguageSpec, BaseLanguageAdapter
from engine.language.python.plugin import PythonPlugin
from engine.language.python.adapter import PythonLanguageAdapter
from engine.language.java.plugin import JavaPlugin
from engine.language.java.adapter import JavaLanguageAdapter


def test_python_plugin_spec():
    """Verify PythonPlugin metadata."""
    plugin = PythonPlugin()

    assert plugin.spec.id == "python"
    assert ".py" in plugin.spec.extensions
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
    assert ".java" in plugin.spec.extensions
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

    assert python_plugin.spec.id == "python"
    assert java_plugin.spec.id == "java"

from typing import Any

import pytest

from core.errors import (
    LanguageDetectionFailed,
    LanguageNotSupported,
    LanguageRegistrationError,
)
from engine.language.base import BaseLanguageAdapter, FileContext, LanguageSpec
from engine.language.builtins import create_default_language_registry
from engine.language.detection import LanguageDetector
from engine.language.java.plugin import JavaPlugin
from engine.language.python.adapter import PythonLanguageAdapter
from engine.language.python.plugin import PythonPlugin
from engine.language.registry import LanguageRegistry


class MockPlugin:
    """Mock language plugin for testing custom extensions/filenames."""

    def __init__(self, id: str, extensions: set[str], filenames: set[str] | None = None):
        self.spec = LanguageSpec(
            id=id,
            extensions=frozenset(extensions),
            filenames=frozenset(filenames or set()),
        )
        self.adapter_created = False

    def create_adapter(self) -> BaseLanguageAdapter:
        self.adapter_created = True
        return None  # type: ignore


def test_registry_register_and_get():
    """Verify basic registration and retrieval of plugins."""
    registry = LanguageRegistry()
    python_plugin = PythonPlugin()
    java_plugin = JavaPlugin()

    registry.register(python_plugin)
    registry.register(java_plugin)

    assert registry.get("python") is python_plugin
    assert registry.get("java") is java_plugin

    with pytest.raises(LanguageNotSupported):
        registry.get("invalid-lang")


def test_registry_create_adapter():
    """Verify adapter instantiation via create_adapter."""
    registry = LanguageRegistry()
    python_plugin = PythonPlugin()
    registry.register(python_plugin)

    adapter = registry.create_adapter("python")
    assert isinstance(adapter, PythonLanguageAdapter)

    with pytest.raises(LanguageNotSupported):
        registry.create_adapter("invalid-lang")


def test_registry_resolves_python_extension():
    """Verify that registry resolves python extension."""
    registry = create_default_language_registry()
    plugin = registry.find_by_extension(".py")
    assert plugin is not None
    assert plugin.spec.id == "python"


def test_registry_resolves_typescript_extensions():
    """Verify that registry resolves typescript extensions."""
    registry = create_default_language_registry()
    plugin_ts = registry.find_by_extension(".ts")
    plugin_tsx = registry.find_by_extension(".tsx")
    assert plugin_ts is not None
    assert plugin_tsx is not None
    assert plugin_ts.spec.id == "typescript"
    assert plugin_tsx.spec.id == "typescript"


def test_registry_resolves_java_extension():
    """Verify that registry resolves java extension."""
    registry = create_default_language_registry()
    plugin = registry.find_by_extension(".java")
    assert plugin is not None
    assert plugin.spec.id == "java"


def test_unknown_extension_returns_none():
    """Verify that unknown extension returns None."""
    registry = create_default_language_registry()
    assert registry.find_by_extension(".unknown") is None


def test_detector_uses_registered_language():
    """Verify that detector uses registered language."""
    registry = LanguageRegistry()
    python_plugin = PythonPlugin()
    registry.register(python_plugin)

    detector = LanguageDetector(registry)
    files = [FileContext(path="main.py", source="print(1)", ast=None, language="")]
    spec = detector.detect(files)

    assert spec.id == "python"


def test_detector_detect_by_filename():
    """Verify language detection by exact filename match."""
    registry = LanguageRegistry()
    dockerfile_plugin = MockPlugin("dockerfile", extensions=set(), filenames={"Dockerfile"})
    registry.register(dockerfile_plugin)

    detector = LanguageDetector(registry)
    files = [
        FileContext(path="path/to/Dockerfile", source="FROM alpine", ast=None, language=""),
    ]
    spec = detector.detect(files)
    assert spec.id == "dockerfile"


def test_detector_detect_by_language_id():
    """Verify language detection by explicit FileContext.language field."""
    registry = LanguageRegistry()
    python_plugin = PythonPlugin()
    registry.register(python_plugin)

    detector = LanguageDetector(registry)
    # Path doesn't match extension/filename, but language ID does
    files = [
        FileContext(path="some_file_without_ext", source="print(1)", ast=None, language="python"),
    ]
    spec = detector.detect(files)
    assert spec.id == "python"


def test_detector_detect_voting():
    """Verify voting behavior and fallback to registration order in case of tie."""
    registry = LanguageRegistry()
    python_plugin = PythonPlugin()
    java_plugin = JavaPlugin()
    registry.register(python_plugin)
    registry.register(java_plugin)

    detector = LanguageDetector(registry)

    # 2 python files, 1 java file -> python should win
    files = [
        FileContext(path="a.py", source="", ast=None, language=""),
        FileContext(path="b.py", source="", ast=None, language=""),
        FileContext(path="c.java", source="", ast=None, language=""),
    ]
    spec = detector.detect(files)
    assert spec.id == "python"

    # 2 java files, 1 python file -> java should win
    files_java_majority = [
        FileContext(path="a.py", source="", ast=None, language=""),
        FileContext(path="b.java", source="", ast=None, language=""),
        FileContext(path="c.java", source="", ast=None, language=""),
    ]
    spec_java = detector.detect(files_java_majority)
    assert spec_java.id == "java"

    # Tie: 1 python, 1 java file -> python should win due to registration order (priority)
    files_tie = [
        FileContext(path="a.py", source="", ast=None, language=""),
        FileContext(path="b.java", source="", ast=None, language=""),
    ]
    spec_tie = detector.detect(files_tie)
    assert spec_tie.id == "python"


def test_detector_detect_errors():
    """Verify detection errors on empty lists or unknown languages."""
    registry = LanguageRegistry()
    python_plugin = PythonPlugin()
    registry.register(python_plugin)

    detector = LanguageDetector(registry)

    # Empty files list
    with pytest.raises(LanguageDetectionFailed) as exc_info:
        detector.detect([])
    assert "No files provided" in str(exc_info.value)

    # Unknown files
    with pytest.raises(LanguageDetectionFailed) as exc_info:
        detector.detect([FileContext(path="unknown.xyz", source="", ast=None, language="")])
    assert "Could not detect any registered language plugin" in str(exc_info.value)


def test_duplicate_id_is_rejected():
    """Verify that duplicate language ID registration is rejected."""
    registry = LanguageRegistry()
    python_plugin = PythonPlugin()
    registry.register(python_plugin)

    with pytest.raises(LanguageRegistrationError) as exc_info:
        registry.register(PythonPlugin())
    assert "already registered" in str(exc_info.value)


def test_duplicate_extension_is_rejected():
    """Verify that duplicate extension registration is rejected."""
    registry = LanguageRegistry()
    python_plugin = PythonPlugin()
    registry.register(python_plugin)

    class DuplicateExtensionPlugin:
        spec = LanguageSpec(
            id="another-python",
            extensions=frozenset({".py"}),
        )

        def create_adapter(self) -> BaseLanguageAdapter:
            return None  # type: ignore

    with pytest.raises(LanguageRegistrationError) as exc_info:
        registry.register(DuplicateExtensionPlugin())
    assert "already registered by 'python'" in str(exc_info.value)


def test_critical_architectural_boundary():
    """Verify that language detection does not require concrete adapter instantiation."""
    class FakePlugin:
        spec = LanguageSpec(
            id="fake",
            extensions=frozenset({".fake"}),
        )

        def create_adapter(self) -> BaseLanguageAdapter:
            raise AssertionError("Detector must not create adapters")

    registry = LanguageRegistry()
    registry.register(FakePlugin())

    detector = LanguageDetector(registry)
    files = [FileContext(path="test.fake", source="", ast=None, language="")]
    
    spec = detector.detect(files)
    assert spec.id == "fake"


def test_end_to_end_path():
    """Verify that detector, registry, plugin, and adapter work end-to-end with compilation."""
    registry = create_default_language_registry()
    detector = LanguageDetector(registry)

    files = {
        "checkout/service.py": "def confirm_checkout(): pass",
    }
    file_contexts = [
        FileContext(path=path, source=content, ast=None, language="")
        for path, content in files.items()
    ]

    spec = detector.detect(file_contexts)
    assert spec.id == "python"

    plugin = registry.get(spec.id)
    adapter = plugin.create_adapter()
    assert isinstance(adapter, PythonLanguageAdapter)

    model = adapter.compile({"files": files})
    assert model is not None
    assert len(model.symbols) > 0


def test_registry_validation():
    """Verify validation when registering malformed plugins."""
    registry = LanguageRegistry()

    # None plugin
    with pytest.raises(ValueError):
        registry.register(None)  # type: ignore

    # Plugin without spec
    class BadPluginNoSpec:
        pass
    with pytest.raises(ValueError):
        registry.register(BadPluginNoSpec())  # type: ignore

    # Plugin with empty ID
    class BadPluginEmptyId:
        class FakeSpec:
            id = ""
            extensions = frozenset()
            filenames = frozenset()
        spec = FakeSpec()
    with pytest.raises(ValueError):
        registry.register(BadPluginEmptyId())  # type: ignore


def test_default_registry_contains_builtin_languages():
    registry = create_default_language_registry()

    assert registry.get("python").spec.id == "python"
    assert registry.get("typescript").spec.id == "typescript"
    assert registry.get("java").spec.id == "java"


def test_default_registry_resolves_builtin_extensions():
    registry = create_default_language_registry()

    assert registry.find_by_extension(".py").spec.id == "python"
    assert registry.find_by_extension(".ts").spec.id == "typescript"
    assert registry.find_by_extension(".tsx").spec.id == "typescript"
    assert registry.find_by_extension(".java").spec.id == "java"


def test_default_registry_creates_python_adapter():
    registry = create_default_language_registry()

    adapter = registry.get("python").create_adapter()

    assert isinstance(adapter, PythonLanguageAdapter)


def test_default_registry_contains_typescript_plugin():
    registry = create_default_language_registry()

    plugin = registry.get("typescript")

    assert plugin.spec.id == "typescript"


def test_generic_registry_accepts_arbitrary_plugins():
    class FakeAdapter(BaseLanguageAdapter):
        def compile(self, repository_input, **kwargs):
            return None
        def get_language(self) -> str:
            return "fake"
        def get_compiler_passes(self) -> list[str]:
            return []
        def _index_single_file(self, file_path: str, content: str, language: str) -> Any:
            return None

    class FakeLanguagePlugin:
        spec = LanguageSpec(
            id="fake",
            extensions=frozenset({".fake"}),
        )

        def create_adapter(self) -> BaseLanguageAdapter:
            return FakeAdapter()

    registry = LanguageRegistry()
    registry.register(FakeLanguagePlugin())

    assert registry.get("fake").spec.id == "fake"
    assert registry.find_by_extension(".fake").spec.id == "fake"
    assert isinstance(registry.get("fake").create_adapter(), FakeAdapter)

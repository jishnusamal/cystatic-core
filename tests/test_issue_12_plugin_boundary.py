"""Test suite for Issue 12: plugin and language registry boundary."""

import pytest
from core.errors import (
    LanguageDetectionFailed,
    LanguageNotSupported,
    LanguageRegistrationError,
)
from engine.language.base import (
    BaseLanguageAdapter,
    FileContext,
    LanguagePlugin,
    LanguageSpec,
)
from engine.language.builtins import create_default_language_registry
from engine.language.detection import LanguageDetector
from engine.language.java.adapter import JavaLanguageAdapter
from engine.language.java.plugin import JavaPlugin
from engine.language.python.adapter import PythonLanguageAdapter
from engine.language.python.plugin import PythonPlugin
from engine.language.registry import LanguageRegistry
from engine.language.typescript.adapter import TypeScriptLanguageAdapter
from engine.language.typescript.plugin import TypeScriptPlugin


class DummyPlugin:
    """A dummy language plugin for testing registry functionality."""

    def __init__(self, id: str, extensions: set[str], filenames: set[str] | None = None):
        self.spec = LanguageSpec(
            id=id,
            extensions=frozenset(extensions),
            filenames=frozenset(filenames or set()),
        )

    def create_adapter(self) -> BaseLanguageAdapter:
        return None  # type: ignore


# --- 1. Registry Tests ---


def test_registry_register_plugin():
    """Verify that we can register a custom plugin."""
    registry = LanguageRegistry()
    dummy = DummyPlugin("dummy", {".dum"})

    registry.register(dummy)
    assert registry.get("dummy") is dummy


def test_registry_retrieve_plugin():
    """Verify retrieval of plugins by language ID."""
    registry = create_default_language_registry()

    python_plugin = registry.get("python")
    java_plugin = registry.get("java")
    typescript_plugin = registry.get("typescript")

    assert isinstance(python_plugin, PythonPlugin)
    assert isinstance(java_plugin, JavaPlugin)
    assert isinstance(typescript_plugin, TypeScriptPlugin)


def test_registry_reject_duplicate_ids():
    """Verify that registering duplicate language IDs raises LanguageRegistrationError."""
    registry = LanguageRegistry()
    dummy1 = DummyPlugin("dummy", {".dum1"})
    dummy2 = DummyPlugin("dummy", {".dum2"})

    registry.register(dummy1)
    with pytest.raises(LanguageRegistrationError) as exc_info:
        registry.register(dummy2)
    assert "already registered" in str(exc_info.value)


def test_registry_resolve_by_extension():
    """Verify that plugins are correctly resolved by extension."""
    registry = create_default_language_registry()

    assert registry.find_by_extension(".py").spec.id == "python"
    assert registry.find_by_extension(".java").spec.id == "java"
    assert registry.find_by_extension(".ts").spec.id == "typescript"
    assert registry.find_by_extension(".tsx").spec.id == "typescript"
    assert registry.find_by_extension(".nonexistent") is None


def test_registry_resolve_by_filename():
    """Verify that plugins can be resolved by filename."""
    registry = LanguageRegistry()
    docker_plugin = DummyPlugin("dockerfile", set(), {"Dockerfile"})
    registry.register(docker_plugin)

    resolved = registry.find_by_filename("Dockerfile")
    assert resolved is docker_plugin
    assert registry.find_by_filename("NotDockerfile") is None


def test_registry_reject_unsupported():
    """Verify that requesting an unsupported language raises LanguageNotSupported."""
    registry = create_default_language_registry()

    with pytest.raises(LanguageNotSupported):
        registry.get("unsupported-lang")

    with pytest.raises(LanguageNotSupported):
        registry.create_adapter("unsupported-lang")


# --- 2. Detection Tests ---


def test_detection_py_to_python():
    """Verify .py files detect as Python."""
    registry = create_default_language_registry()
    detector = LanguageDetector(registry)

    files = [FileContext(path="main.py", source="print('hello')", ast=None, language="")]
    spec = detector.detect(files)
    assert spec.id == "python"


def test_detection_ts_to_typescript():
    """Verify .ts files detect as TypeScript."""
    registry = create_default_language_registry()
    detector = LanguageDetector(registry)

    files = [FileContext(path="index.ts", source="const x = 1;", ast=None, language="")]
    spec = detector.detect(files)
    assert spec.id == "typescript"


def test_detection_tsx_to_typescript():
    """Verify .tsx files detect as TypeScript."""
    registry = create_default_language_registry()
    detector = LanguageDetector(registry)

    files = [FileContext(path="App.tsx", source="const App = () => null;", ast=None, language="")]
    spec = detector.detect(files)
    assert spec.id == "typescript"


def test_detection_java_to_java():
    """Verify .java files detect as Java."""
    registry = create_default_language_registry()
    detector = LanguageDetector(registry)

    files = [FileContext(path="Service.java", source="class Service {}", ast=None, language="")]
    spec = detector.detect(files)
    assert spec.id == "java"


def test_detection_mixed_scoring():
    """Verify voting behavior in a mixed repository."""
    registry = create_default_language_registry()
    detector = LanguageDetector(registry)

    # 3 Python files and 1 Java file should resolve to Python
    files = [
        FileContext(path="a.py", source="", ast=None, language=""),
        FileContext(path="b.py", source="", ast=None, language=""),
        FileContext(path="c.py", source="", ast=None, language=""),
        FileContext(path="d.java", source="", ast=None, language=""),
    ]
    spec = detector.detect(files)
    assert spec.id == "python"


def test_detection_unsupported_only():
    """Verify that a repository with only unsupported files raises LanguageDetectionFailed."""
    registry = create_default_language_registry()
    detector = LanguageDetector(registry)

    files = [
        FileContext(path="document.pdf", source="", ast=None, language=""),
        FileContext(path="style.css", source="", ast=None, language=""),
    ]
    with pytest.raises(LanguageDetectionFailed):
        detector.detect(files)


# --- 3. Plugin Construction Tests ---


def test_plugin_construction_python():
    """Verify PythonPlugin returns PythonLanguageAdapter."""
    plugin = PythonPlugin()
    adapter = plugin.create_adapter()
    assert isinstance(adapter, PythonLanguageAdapter)


def test_plugin_construction_typescript():
    """Verify TypeScriptPlugin returns TypeScriptLanguageAdapter."""
    plugin = TypeScriptPlugin()
    adapter = plugin.create_adapter()
    assert isinstance(adapter, TypeScriptLanguageAdapter)


def test_plugin_construction_java():
    """Verify JavaPlugin returns JavaLanguageAdapter."""
    plugin = JavaPlugin()
    adapter = plugin.create_adapter()
    assert isinstance(adapter, JavaLanguageAdapter)


# --- 4. Compilation Compatibility Tests ---


def test_compilation_compatibility():
    """Verify that:

    Plugin -> Adapter -> RepositoryIndex -> SemanticCompiler -> RepositoryModel
    produces the same results as compiling directly via adapter.compile().
    """
    registry = create_default_language_registry()
    plugin = registry.get("python")
    adapter = plugin.create_adapter()

    # Define a simple python project
    repository_input = {
        "files": {
            "main.py": (
                "def start():\n"
                "    helper()\n"
            ),
            "utils.py": (
                "def helper():\n"
                "    pass\n"
            )
        },
        "language": "python",
    }

    # Flow 1: Compile directly via adapter
    model_direct = adapter.compile(repository_input)

    # Flow 2: Explicit step-by-step pipeline translation
    # 1. Build RepositoryIndex
    index = adapter.build_index(repository_input)
    # 2. Compile to RepositoryModel via SemanticCompiler
    from engine.language.base.semantic_compiler import SemanticCompiler
    semantic_compiler = SemanticCompiler()
    model_pipelined = semantic_compiler.compile(index, "python")

    # Assert compatibility
    assert len(model_direct.symbols) == len(model_pipelined.symbols)
    assert {s.id for s in model_direct.symbols} == {s.id for s in model_pipelined.symbols}
    assert {e.caller_id for e in model_direct.call_graph.edges} == {e.caller_id for e in model_pipelined.call_graph.edges}
    assert {e.callee_id for e in model_direct.call_graph.edges} == {e.callee_id for e in model_pipelined.call_graph.edges}


# --- 5. Incremental Compilation Tests ---


def test_incremental_compilation_preservation():
    """Verify that plugin-created adapters preserve existing compile_incremental() and GraphPatcher behavior."""
    registry = create_default_language_registry()
    plugin = registry.get("python")
    adapter = plugin.create_adapter()

    # Initial revision
    base_files = {
        "foo.py": (
            "from other import bar\n"
            "def foo():\n"
            "    bar()\n"
        ),
        "other.py": (
            "def bar():\n"
            "    pass\n"
            "def baz():\n"
            "    pass\n"
        )
    }
    base_graph = adapter.compile_graph({"files": base_files})

    # Head revision with modification
    head_files = {
        "foo.py": (
            "from other import baz\n"
            "def foo():\n"
            "    baz()\n"
        ),
        "other.py": (
            "def bar():\n"
            "    pass\n"
            "def baz():\n"
            "    pass\n"
        )
    }

    # Perform incremental compile
    patched_graph = adapter.compile_incremental(base_graph, {"files": head_files})
    assert patched_graph is not None

    # Verify GraphPatcher correctly updated base graph structures
    model = patched_graph.to_model()
    calls = model.get_calls_for("python://foo.py::foo")
    callees = {c.callee_id for c in calls}

    # Edge to bar must be removed, and edge to baz must be added
    assert "python://other.py::bar" not in callees
    assert "python://other.py::baz" in callees

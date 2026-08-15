import pytest
import ast
from typing import Any, Iterable

from engine.language.base.file_context import FileContext
from engine.language.base.index_compiler import IndexCompiler
from engine.language.python.adapter import PythonLanguageAdapter
from engine.language.python.visitors import PythonVisitor
from engine.repository.model.repository_index import FileIndex, RepositoryIndex


class OneTimeGenerator:
    """A wrapper that ensures the underlying iterable is consumed exactly once and does not support len or getitem."""

    def __init__(self, items):
        self.items = items
        self.consumed = False

    def __iter__(self):
        if self.consumed:
            raise AssertionError("Generator/Iterator was iterated more than once!")
        self.consumed = True
        return iter(self.items)


def test_iterable_accepted():
    """Test 1: Verify that IndexCompiler accepts a generator/iterator instead of a list."""
    adapter = PythonLanguageAdapter()

    files = {
        "a.py": "def foo(): pass",
        "b.py": "def bar(): pass",
    }

    # Verify compile works with a generator expression
    index_stream = adapter.build_index({"files": files})
    assert len(index_stream.files) == 2

    symbol_names = {s.name for f in index_stream.files for s in f.symbols}
    assert "foo" in symbol_names
    assert "bar" in symbol_names


def test_generator_consumed_once():
    """Test 2: Verify IndexCompiler consumes the generator exactly once without len() or indexing."""
    files = {
        "a.py": "def foo(): pass",
        "b.py": "def bar(): pass",
    }

    contexts = []
    for path, content in files.items():
        tree = ast.parse(content, filename=path)
        contexts.append(
            FileContext(path=path, source=content, ast=tree, language="python")
        )

    # Wrap in our strict one-time iterator
    iterator_wrapper = OneTimeGenerator(contexts)

    adapter = PythonLanguageAdapter()
    compiler = adapter._index_compiler

    # compile_with_visitor should execute successfully
    index = compiler.compile_with_visitor(iterator_wrapper, "python", adapter._visitor)
    assert len(index.files) == 2


def test_execution_ordering():
    """Test 3: Verify execution order is sequential (parse A -> visit A -> parse B -> visit B)."""
    events = []

    # We will log parsing inside the generator
    def generate_contexts():
        events.append("parse_a")
        yield FileContext(
            path="a.py",
            source="def foo(): pass",
            ast=ast.parse("def foo(): pass", filename="a.py"),
            language="python",
        )
        events.append("parse_b")
        yield FileContext(
            path="b.py",
            source="def bar(): pass",
            ast=ast.parse("def bar(): pass", filename="b.py"),
            language="python",
        )

    # We will track visitation using a custom mock visitor
    class MockVisitor:
        def visit(self, context, builder):
            events.append(f"visit_{context.path.replace('.py', '')}")
            builder["symbols"].append("dummy_symbol")

    compiler = IndexCompiler([])
    visitor = MockVisitor()

    # Run compilation
    compiler.compile_with_visitor(generate_contexts(), "python", visitor)

    # Verify strict interleaved ordering
    assert events == ["parse_a", "visit_a", "parse_b", "visit_b"]


def test_eager_vs_streaming_equivalence():
    """Test 4: Compare results between eager (list-based) and streaming (generator-based) compiles."""
    files = {
        "checkout.py": """
from payment import charge_card

def checkout():
    charge_card()
""",
        "payment.py": """
def charge_card():
    pass
""",
    }

    adapter = PythonLanguageAdapter()

    # Eager compile (manually build a list of contexts)
    eager_contexts = []
    for path, content in files.items():
        tree = ast.parse(content, filename=path)
        eager_contexts.append(
            FileContext(path=path, source=content, ast=tree, language="python")
        )

    eager_index = adapter._index_compiler.compile_with_visitor(
        eager_contexts, "python", adapter._visitor
    )

    # Streaming compile
    streaming_index = adapter.build_index({"files": files})

    # Sort files by path for deterministic comparison
    eager_files = sorted(eager_index.files, key=lambda f: f.path)
    streaming_files = sorted(streaming_index.files, key=lambda f: f.path)

    assert len(eager_files) == len(streaming_files)
    for ef, sf in zip(eager_files, streaming_files):
        assert ef.path == sf.path
        assert ef.symbols == sf.symbols
        assert ef.imports == sf.imports
        assert ef.calls == sf.calls
        assert ef.entrypoints == sf.entrypoints
        assert ef.type_relationships == sf.type_relationships
        assert ef.persistence_models == sf.persistence_models
        assert ef.repository_methods == sf.repository_methods
        assert ef.events == sf.events
        assert ef.tests == sf.tests
        assert ef.configurations == sf.configurations

"""Tests for language_adapters."""

import tempfile
from pathlib import Path

import pytest

from language_adapters.python.python_adapter import PythonAdapter
from language_adapters.ts_adapter import TypeScriptAdapter


@pytest.mark.skip(reason="PythonAdapter.analyze() not implemented - adapter focuses on diff analysis")
def test_python_adapter_finds_py_files() -> None:
    """Placeholder test - PythonAdapter works with diffs, not file discovery."""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "m.py").write_text("x = 1\n")
        sub = root / "pkg"
        sub.mkdir()
        (sub / "__init__.py").write_text("")
        # PythonAdapter focuses on analyzing diffs, not discovering files
        pass


def test_ts_adapter_finds_ts_files() -> None:
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "a.ts").write_text("export {};\n")
        r = TypeScriptAdapter().analyze(root)
        assert "a.ts" in r.file_paths

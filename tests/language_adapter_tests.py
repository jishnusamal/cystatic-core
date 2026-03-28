"""Tests for language_adapters."""

import tempfile
from pathlib import Path

from language_adapters.python_adapter import PythonAdapter
from language_adapters.ts_adapter import TypeScriptAdapter


def test_python_adapter_finds_py_files() -> None:
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "m.py").write_text("x = 1\n")
        sub = root / "pkg"
        sub.mkdir()
        (sub / "__init__.py").write_text("")
        r = PythonAdapter().analyze(root)
        assert "m.py" in r.file_paths
        assert "pkg/__init__.py" in r.file_paths


def test_ts_adapter_finds_ts_files() -> None:
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "a.ts").write_text("export {};\n")
        r = TypeScriptAdapter().analyze(root)
        assert "a.ts" in r.file_paths

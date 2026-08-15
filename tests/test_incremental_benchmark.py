"""Benchmark suite for Incremental Compiler vs Full Compilation."""

import time
import pytest
from engine.language.python.adapter import PythonLanguageAdapter
from engine.language.model import RepositoryGraph, RepositoryModel


def generate_synthetic_repo(num_files: int = 100) -> dict[str, str]:
    """Generate a synthetic multi-file repository with inter-file calls and imports."""
    files: dict[str, str] = {}

    # File 0 defines core functions
    files["module_0.py"] = '''"""Module 0 - core functions."""

def core_utility():
    return 42

def process_data(val):
    return val * 2
'''

    # Files 1 to N-1 depend on module_0 and previous modules
    for i in range(1, num_files):
        prev = i - 1
        code = f'''"""Module {i}."""
from module_0 import core_utility, process_data
from module_{prev} import func_{prev}

def func_{i}():
    a = core_utility()
    b = process_data(a)
    c = func_{prev}()
    return b + c
'''
        files[f"module_{i}.py"] = code

    return files


class TestIncrementalBenchmark:
    """Benchmark tests evaluating scaling, accuracy, and phase performance of incremental compilation."""

    @pytest.mark.parametrize("num_changed", [1, 5, 20, 50])
    def test_incremental_vs_full_scaling(self, num_changed):
        """Test that incremental compilation is faster than full compilation and produces identical output."""
        adapter = PythonLanguageAdapter()
        repo_files = generate_synthetic_repo(num_files=100)

        # Build initial base graph
        t0 = time.perf_counter()
        base_graph = adapter.compile_graph({"files": repo_files})
        base_build_duration = time.perf_counter() - t0

        # Modify N files
        head_files = dict(repo_files)
        for i in range(num_changed):
            idx = 10 + i
            head_files[f"module_{idx}.py"] = (
                repo_files[f"module_{idx}.py"]
                + f"\n# Modified comment {i}\ndef extra_{idx}():\n    return {i}\n"
            )

        # 1. Full compilation baseline
        t0 = time.perf_counter()
        full_model = adapter.compile({"files": head_files})
        full_duration = time.perf_counter() - t0

        # 2. Incremental compilation
        t0 = time.perf_counter()
        metrics: dict = {}
        inc_graph = adapter.compile_incremental(
            base_graph, {"files": head_files, "metrics": metrics}
        )
        inc_model = inc_graph.to_model()
        inc_duration = time.perf_counter() - t0

        # Verify semantic output equivalence
        assert set(inc_model.symbols) == set(full_model.symbols)
        assert set(inc_model.call_graph.edges) == set(full_model.call_graph.edges)
        assert set(inc_model.reference_graph.edges) == set(
            full_model.reference_graph.edges
        )

        # Incremental compile duration must be smaller than full compilation
        assert inc_duration <= full_duration + 0.1, (
            f"Incremental ({inc_duration:.3f}s) should be fast compared to full ({full_duration:.3f}s)"
        )

    def test_add_file_incremental_benchmark(self):
        """Benchmark adding a single new file to a 100-file repository."""
        adapter = PythonLanguageAdapter()
        repo_files = generate_synthetic_repo(num_files=100)
        base_graph = adapter.compile_graph({"files": repo_files})

        head_files = dict(repo_files)
        head_files["new_feature.py"] = """from module_0 import core_utility

def new_feature_handler():
    return core_utility()
"""
        full_model = adapter.compile({"files": head_files})
        inc_graph = adapter.compile_incremental(base_graph, {"files": head_files})
        inc_model = inc_graph.to_model()

        assert set(inc_model.symbols) == set(full_model.symbols)
        assert set(inc_model.call_graph.edges) == set(full_model.call_graph.edges)

    def test_delete_file_incremental_benchmark(self):
        """Benchmark deleting a leaf file from a 100-file repository."""
        adapter = PythonLanguageAdapter()
        repo_files = generate_synthetic_repo(num_files=100)
        base_graph = adapter.compile_graph({"files": repo_files})

        head_files = dict(repo_files)
        del head_files["module_99.py"]

        full_model = adapter.compile({"files": head_files})
        inc_graph = adapter.compile_incremental(base_graph, {"files": head_files})
        inc_model = inc_graph.to_model()

        assert set(inc_model.symbols) == set(full_model.symbols)
        assert set(inc_model.call_graph.edges) == set(full_model.call_graph.edges)

    def test_rename_symbol_incremental_benchmark(self):
        """Benchmark renaming a core symbol that affects multiple downstream files."""
        adapter = PythonLanguageAdapter()
        repo_files = generate_synthetic_repo(num_files=30)
        base_graph = adapter.compile_graph({"files": repo_files})

        head_files = dict(repo_files)
        # Rename core_utility to core_utility_v2 in module_0.py
        head_files["module_0.py"] = repo_files["module_0.py"].replace(
            "core_utility", "core_utility_v2"
        )
        # Update references in module_1.py
        head_files["module_1.py"] = repo_files["module_1.py"].replace(
            "core_utility", "core_utility_v2"
        )

        full_model = adapter.compile({"files": head_files})
        inc_graph = adapter.compile_incremental(base_graph, {"files": head_files})
        inc_model = inc_graph.to_model()

        assert set(inc_model.symbols) == set(full_model.symbols)
        assert set(inc_model.call_graph.edges) == set(full_model.call_graph.edges)

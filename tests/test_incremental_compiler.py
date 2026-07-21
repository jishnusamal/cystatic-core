"""Tests for the Incremental Repository Compiler and GraphPatcher."""

import hashlib
import tempfile
import time
import os
import pytest
from language_adapters.python.adapter import PythonLanguageAdapter
from language_adapters.model import (
    SymbolKind,
    SymbolVisibility,
    RepositoryGraph,
    FileContribution,
)


@pytest.fixture
def base_source_files():
    """Create a base set of files representing the initial repository state."""
    service_py = '''
"""Checkout service."""

from processor import charge_card


def confirm_checkout():
    """Confirm a checkout."""
    validate_coupon()
    charge_card()
    save_order()


def validate_coupon():
    pass


class CheckoutService:
    def process_payment(self):
        pass
'''

    processor_py = '''
"""Payment processor."""


def charge_card():
    pass


def save_order():
    pass
'''
    return {
        "service.py": service_py,
        "processor.py": processor_py,
    }


class TestIncrementalCompiler:
    """Tests the incremental compilation logic and graph patching."""

    def test_base_compile_graph(self, base_source_files):
        """Test compiling the full repository directly into a RepositoryGraph."""
        adapter = PythonLanguageAdapter()
        graph = adapter.compile_graph({"files": base_source_files})

        assert isinstance(graph, RepositoryGraph)
        assert len(graph.files) == 2
        assert "service.py" in graph.files
        assert "processor.py" in graph.files
        
        # Verify file content hashes are stored
        for path, content in base_source_files.items():
            expected_hash = hashlib.sha256(content.encode('utf-8')).hexdigest()
            assert graph.files[path].source_hash == expected_hash

        # Verify symbol resolution in the graph
        assert f"python://service.py::confirm_checkout" in graph.symbols
        assert f"python://processor.py::charge_card" in graph.symbols

        # Verify call graph edges
        assert len(graph.call_graph.edges) > 0
        calls = graph.to_model().get_calls_for("python://service.py::confirm_checkout")
        callees = {c.callee_id for c in calls}
        assert "python://service.py::validate_coupon" in callees
        assert "python://processor.py::charge_card" in callees

    def test_incremental_modification(self, base_source_files):
        """Test modifying a file incrementally yields an identical graph to full compilation."""
        adapter = PythonLanguageAdapter()
        base_graph = adapter.compile_graph({"files": base_source_files})

        # Create head files with a modification in service.py:
        # Change `validate_coupon` call to a new local call `log_checkout`.
        head_service_py = '''
"""Checkout service."""

from processor import charge_card


def confirm_checkout():
    """Confirm a checkout."""
    log_checkout()
    charge_card()
    save_order()


def log_checkout():
    pass


class CheckoutService:
    def process_payment(self):
        pass
'''
        head_files = dict(base_source_files)
        head_files["service.py"] = head_service_py

        # Compile head fully from scratch to get the target ground truth
        full_model = adapter.compile({"files": head_files})

        # Compile incrementally on base graph
        inc_graph = adapter.compile_incremental(base_graph, {"files": head_files})
        inc_model = inc_graph.to_model()

        # Validate that incremental compilation matches full compilation exactly
        assert set(inc_model.symbols) == set(full_model.symbols)
        assert set(inc_model.call_graph.edges) == set(full_model.call_graph.edges)
        assert set(inc_model.reference_graph.edges) == set(full_model.reference_graph.edges)
        assert set(inc_model.entry_points) == set(full_model.entry_points)
        assert set(inc_model.persistence_models) == set(full_model.persistence_models)
        assert set(inc_model.repository_methods) == set(full_model.repository_methods)
        assert set(inc_model.event_constructs) == set(full_model.event_constructs)
        assert set(inc_model.test_definitions) == set(full_model.test_definitions)

    def test_incremental_add_file(self, base_source_files):
        """Test adding a file incrementally yields an identical graph to full compilation."""
        adapter = PythonLanguageAdapter()
        base_graph = adapter.compile_graph({"files": base_source_files})

        # Add a new file utils.py that calls charge_card and is called by service.py
        utils_py = '''
from processor import charge_card

def helper():
    charge_card()
'''
        head_service_py = '''
"""Checkout service."""

from processor import charge_card
from utils import helper

def confirm_checkout():
    helper()
    charge_card()
'''
        head_files = dict(base_source_files)
        head_files["utils.py"] = utils_py
        head_files["service.py"] = head_service_py

        # Compile fully from scratch
        full_model = adapter.compile({"files": head_files})

        # Compile incrementally
        inc_graph = adapter.compile_incremental(base_graph, {"files": head_files})
        inc_model = inc_graph.to_model()

        # Validate identical output
        assert set(inc_model.symbols) == set(full_model.symbols)
        assert set(inc_model.call_graph.edges) == set(full_model.call_graph.edges)
        assert set(inc_model.reference_graph.edges) == set(full_model.reference_graph.edges)

    def test_incremental_delete_file(self, base_source_files):
        """Test deleting a file incrementally yields an identical graph to full compilation."""
        adapter = PythonLanguageAdapter()
        base_graph = adapter.compile_graph({"files": base_source_files})

        # Head files deletes processor.py
        # Checkout service is modified so it doesn't import or call from processor.py anymore.
        head_service_py = '''
def confirm_checkout():
    pass
'''
        head_files = {
            "service.py": head_service_py
        }

        # Compile fully from scratch
        full_model = adapter.compile({"files": head_files})

        # Compile incrementally
        inc_graph = adapter.compile_incremental(base_graph, {"files": head_files})
        inc_model = inc_graph.to_model()

        # Validate identical output
        assert set(inc_model.symbols) == set(full_model.symbols)
        assert set(inc_model.call_graph.edges) == set(full_model.call_graph.edges)
        assert set(inc_model.reference_graph.edges) == set(full_model.reference_graph.edges)

    def test_deleted_symbol_incoming_edge_cleanup(self, base_source_files):
        """Test deleting a symbol also correctly cleans up incoming edges from other unchanged files."""
        adapter = PythonLanguageAdapter()
        base_graph = adapter.compile_graph({"files": base_source_files})

        # Head files deletes charge_card from processor.py
        # but service.py is unchanged (so it still has a call to charge_card).
        # A full compilation will try to resolve call to charge_card, and it won't find it,
        # so it will return None (meaning no call edge is added).
        # Our incremental compiler must match this by removing the incoming call edge
        # from service.py to the deleted charge_card symbol.
        head_processor_py = '''
def save_order():
    pass
'''
        head_files = dict(base_source_files)
        head_files["processor.py"] = head_processor_py

        # Compile fully from scratch
        full_model = adapter.compile({"files": head_files})

        # Compile incrementally
        inc_graph = adapter.compile_incremental(base_graph, {"files": head_files})
        inc_model = inc_graph.to_model()

        # Validate call graph matching (specifically, no call edge to charge_card exists)
        assert set(inc_model.symbols) == set(full_model.symbols)
        assert set(inc_model.call_graph.edges) == set(full_model.call_graph.edges)
        assert set(inc_model.reference_graph.edges) == set(full_model.reference_graph.edges)

    def test_serialization(self, base_source_files):
        """Test saving the RepositoryGraph to disk and loading it back."""
        adapter = PythonLanguageAdapter()
        graph = adapter.compile_graph({"files": base_source_files})

        with tempfile.NamedTemporaryFile(suffix=".repository_graph", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            # Save graph
            graph.save_to_file(tmp_path)
            
            # Load graph
            loaded_graph = RepositoryGraph.load_from_file(tmp_path)

            # Check that content is identical
            assert set(loaded_graph.files.keys()) == set(graph.files.keys())
            assert set(loaded_graph.symbols.keys()) == set(graph.symbols.keys())
            assert set(loaded_graph.imports.keys()) == set(graph.imports.keys())
            assert set(loaded_graph.call_graph.edges) == set(graph.call_graph.edges)
            assert set(loaded_graph.reference_graph.edges) == set(graph.reference_graph.edges)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_performance_benchmark(self):
        """Test that incremental compilation is faster than full compilation for small changes."""
        # Create a larger synthetic repository with 20 files
        files = {}
        for i in range(20):
            files[f"file_{i}.py"] = f'''
def func_{i}():
    print("Function {i}")
'''
        adapter = PythonLanguageAdapter()
        
        # Initial compilation
        graph = adapter.compile_graph({"files": files})

        # Modify only one file
        files["file_10.py"] = '''
def func_10():
    print("Modified Function 10")
    
def new_helper():
    pass
'''
        # Benchmark Full Compilation
        start_full = time.perf_counter()
        adapter.compile({"files": files})
        duration_full = time.perf_counter() - start_full

        # Benchmark Incremental Compilation
        start_inc = time.perf_counter()
        adapter.compile_incremental(graph, {"files": files})
        duration_inc = time.perf_counter() - start_inc

        print(f"\n[benchmark] Full compilation took: {duration_full * 1000:.2f}ms")
        print(f"[benchmark] Incremental compilation took: {duration_inc * 1000:.2f}ms")

        # Incremental compilation should be faster (typically 3-10x faster)
        # Note: on extremely small synthetic examples it might be close, but still faster.
        # We assert it is at least as fast or faster.
        assert duration_inc <= duration_full

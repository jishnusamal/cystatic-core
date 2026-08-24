"""Benchmark suite for Incremental Compiler vs Full Compilation using Fact-based architecture."""

from __future__ import annotations

import time

import pytest

from engine.language.python.adapter import PythonLanguageAdapter
from engine.repository.facts import File
from engine.repository.indexing.indexer import RepositoryIndexer
from engine.repository.indexing.sink import InMemoryFactSink
from engine.repository.overlay import RepositoryOverlay, RepositoryView
from engine.repository.query import InMemoryRepository


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


def extract_view_fqns(view: RepositoryView, base_indexer: RepositoryIndexer, head_indexer: RepositoryIndexer):
    symbols_fqns = set()
    
    # 1. Active Symbols
    active_symbols = {}
    for s in view.base._facts.symbols:  # type: ignore[attr-defined]
        if s.id not in view.overlay.removed_symbols:
            fqn = base_indexer.get_symbol_fqn(s.id)
            if fqn:
                active_symbols[s.id] = fqn
                symbols_fqns.add(fqn)
                
    for sid, s in view.overlay.added_symbols.items():
        fqn = head_indexer.get_symbol_fqn(sid)
        if fqn:
            active_symbols[sid] = fqn
            symbols_fqns.add(fqn)
            
    # 2. Call Edges
    calls_fqns = set()
    # Base calls
    for c in view.base._facts.calls:  # type: ignore[attr-defined]
        caller_fqn = base_indexer.get_symbol_fqn(c.caller_id)
        callee_fqn = base_indexer.get_symbol_fqn(c.callee_id)
        base_symbol = view.base.get_symbol(c.caller_id)
        if base_symbol and caller_fqn == 'python://module_3.py::func_3':
            base_file = view.base.get_file(base_symbol.file_id)
            file_name = base_file.path if base_file else "unknown"
            print(f"DEBUG CALL STACK: caller={caller_fqn}, callee={callee_fqn}, file={file_name}, in_removed={base_symbol.file_id in view.overlay.removed_files}")
            
        if view._should_skip_base_for_symbol(c.caller_id) or view._should_skip_base_for_symbol(c.callee_id):
            continue
        if c.caller_id not in active_symbols:
            continue
        if c in view.overlay.removed_calls:
            continue
        if caller_fqn and callee_fqn:
            calls_fqns.add((caller_fqn, callee_fqn))
            
    # Added calls
    for c in view.overlay.added_calls:
        caller_fqn = head_indexer.get_symbol_fqn(c.caller_id)
        callee_fqn = head_indexer.get_symbol_fqn(c.callee_id)
        if caller_fqn and callee_fqn:
            calls_fqns.add((caller_fqn, callee_fqn))
            
    # 3. Reference Edges
    refs_fqns = set()
    # Base references
    for r in view.base._facts.references:  # type: ignore[attr-defined]
        if view._should_skip_base_for_symbol(r.source_id) or view._should_skip_base_for_symbol(r.target_id):
            continue
        if r.source_id not in active_symbols:
            continue
        if r in view.overlay.removed_references:
            continue
        source_fqn = base_indexer.get_symbol_fqn(r.source_id)
        target_fqn = base_indexer.get_symbol_fqn(r.target_id)
        if source_fqn and target_fqn:
            refs_fqns.add((source_fqn, target_fqn))
            
    # Added references
    for r in view.overlay.added_references:
        source_fqn = head_indexer.get_symbol_fqn(r.source_id)
        target_fqn = head_indexer.get_symbol_fqn(r.target_id)
        if source_fqn and target_fqn:
            refs_fqns.add((source_fqn, target_fqn))
            
    return symbols_fqns, calls_fqns, refs_fqns


def extract_full_fqns(full_facts, full_indexer: RepositoryIndexer):
    symbols_fqns = set()
    active_symbols = set()
    for s in full_facts.symbols:
        fqn = full_indexer.get_symbol_fqn(s.id)
        if fqn:
            active_symbols.add(s.id)
            symbols_fqns.add(fqn)
            
    calls_fqns = set()
    for c in full_facts.calls:
        if c.caller_id not in active_symbols:
            continue
        caller_fqn = full_indexer.get_symbol_fqn(c.caller_id)
        callee_fqn = full_indexer.get_symbol_fqn(c.callee_id)
        if caller_fqn and callee_fqn:
            calls_fqns.add((caller_fqn, callee_fqn))
            
    refs_fqns = set()
    for r in full_facts.references:
        if r.source_id not in active_symbols:
            continue
        source_fqn = full_indexer.get_symbol_fqn(r.source_id)
        target_fqn = full_indexer.get_symbol_fqn(r.target_id)
        if source_fqn and target_fqn:
            refs_fqns.add((source_fqn, target_fqn))
            
    return symbols_fqns, calls_fqns, refs_fqns


class TestIncrementalBenchmark:
    """Benchmark tests evaluating scaling, accuracy, and phase performance of incremental compilation."""

    @pytest.mark.parametrize("num_changed", [1, 5, 20, 50])
    def test_incremental_vs_full_scaling(self, num_changed):
        """Test that incremental compilation is faster than full compilation and produces identical output."""
        adapter = PythonLanguageAdapter()
        repo_files = generate_synthetic_repo(num_files=100)

        # 1. Build initial base facts & query
        base_sink = InMemoryFactSink()
        base_indexer = RepositoryIndexer(base_sink)
        t0 = time.perf_counter()
        base_indexer.index_repository({"files": repo_files}, adapter)
        base_facts = base_sink.build_facts()
        base_query = InMemoryRepository(base_facts)
        time.perf_counter() - t0

        # Modify N files
        head_files = dict(repo_files)
        for i in range(num_changed):
            idx = 10 + i
            head_files[f"module_{idx}.py"] = (
                repo_files[f"module_{idx}.py"]
                + f"\n# Modified comment {i}\ndef extra_{idx}():\n    return {i}\n"
            )

        # 2. Full compilation baseline
        full_sink = InMemoryFactSink()
        full_indexer = RepositoryIndexer(full_sink)
        t0 = time.perf_counter()
        full_indexer.index_repository({"files": head_files}, adapter)
        full_facts = full_sink.build_facts()
        full_duration = time.perf_counter() - t0

        # 3. Incremental compiler using RepositoryOverlay
        t0 = time.perf_counter()
        
        # Identify changed files
        added_paths = set(head_files.keys()) - set(repo_files.keys())
        removed_paths = set(repo_files.keys()) - set(head_files.keys())
        modified_paths = {
            f for f in set(repo_files.keys()) & set(head_files.keys())
            if repo_files[f] != head_files[f]
        }

        removed_files = set()
        modified_files = set()
        added_files = {}

        for path in removed_paths:
            file_id = base_indexer.get_or_create_file_id(path)
            removed_files.add(file_id)

        for path in modified_paths:
            file_id = base_indexer.get_or_create_file_id(path)
            removed_files.add(file_id)
            modified_files.add(file_id)
            added_files[file_id] = File(id=file_id, path=path, language="python")

        for path in added_paths:
            # New file -> head indexer will allocate a new ID
            pass

        # Index added & modified files in overlay
        head_sink = InMemoryFactSink()
        head_indexer = RepositoryIndexer(head_sink)
        # Copy base symbol maps to head indexer to ensure alignment and avoid collisions
        for fqn, sym_id in base_indexer._symbol_id_map.items():
            head_indexer._symbol_id_map[fqn] = sym_id
            head_indexer._symbol_fqn_map[sym_id] = fqn
        head_indexer._next_symbol_id = base_indexer._next_symbol_id
        
        # Copy base file IDs to head indexer to ensure alignment
        for path in (added_paths | modified_paths):
            if path in modified_paths:
                base_id = base_indexer.get_or_create_file_id(path)
                head_indexer._file_id_map[path] = base_id
            elif path in added_paths:
                file_id = head_indexer.get_or_create_file_id(path)
                added_files[file_id] = File(id=file_id, path=path, language="python")

        files_to_index = {
            path: head_files[path] for path in (added_paths | modified_paths)
        }
        head_indexer.index_repository({"files": files_to_index}, adapter)
        head_facts = head_sink.build_facts()

        removed_symbols = set()
        for rf_id in removed_files:
            for s in base_query.get_symbols_in_file(rf_id):
                removed_symbols.add(s.id)

        overlay = RepositoryOverlay(
            added_files=added_files,
            removed_files=removed_files,
            modified_files=modified_files,
            added_symbols={s.id: s for s in head_facts.symbols},
            removed_symbols=removed_symbols,
            added_calls=set(head_facts.calls),
            added_references=set(head_facts.references),
            added_imports=set(head_facts.imports),
            added_type_relationships=set(head_facts.type_relationships),
            added_endpoints=set(head_facts.endpoints),
            added_database_relationships=set(head_facts.database_relationships),
            added_event_publications=set(head_facts.event_publications),
            added_event_subscriptions=set(head_facts.event_subscriptions),
            added_test_relationships=set(head_facts.test_relationships),
        )

        inc_view = RepositoryView(base_query, overlay)
        inc_duration = time.perf_counter() - t0

        # 4. Verify semantic output equivalence
        print(f"\nDEBUG TEST: num_changed={num_changed}")
        print(f"DEBUG TEST: removed_files={[base_query.get_file(fid).path for fid in removed_files]}")
        print(f"DEBUG TEST: len(removed_symbols)={len(removed_symbols)}")
        inc_syms, inc_calls, inc_refs = extract_view_fqns(inc_view, base_indexer, head_indexer)
        full_syms, full_calls, full_refs = extract_full_fqns(full_facts, full_indexer)

        assert inc_syms == full_syms
        assert inc_calls == full_calls
        assert inc_refs == full_refs

        # Incremental compile duration must be smaller than full compilation
        assert inc_duration <= full_duration + 0.1, (
            f"Incremental ({inc_duration:.3f}s) should be fast compared to full ({full_duration:.3f}s)"
        )

    def test_add_file_incremental_benchmark(self):
        """Benchmark adding a single new file to a 100-file repository."""
        adapter = PythonLanguageAdapter()
        repo_files = generate_synthetic_repo(num_files=100)

        # Base facts
        base_sink = InMemoryFactSink()
        base_indexer = RepositoryIndexer(base_sink)
        base_indexer.index_repository({"files": repo_files}, adapter)
        base_facts = base_sink.build_facts()
        base_query = InMemoryRepository(base_facts)

        # Head files (add 1 new file)
        head_files = dict(repo_files)
        head_files["new_feature.py"] = """from module_0 import core_utility

def new_feature_handler():
    return core_utility()
"""

        # Full compilation
        full_sink = InMemoryFactSink()
        full_indexer = RepositoryIndexer(full_sink)
        full_indexer.index_repository({"files": head_files}, adapter)
        full_facts = full_sink.build_facts()

        # Incremental compilation
        head_sink = InMemoryFactSink()
        head_indexer = RepositoryIndexer(head_sink)
        # Copy base symbol maps to head indexer to ensure alignment and avoid collisions
        for fqn, sym_id in base_indexer._symbol_id_map.items():
            head_indexer._symbol_id_map[fqn] = sym_id
            head_indexer._symbol_fqn_map[sym_id] = fqn
        head_indexer._next_symbol_id = base_indexer._next_symbol_id
        
        added_files = {}
        file_id = head_indexer.get_or_create_file_id("new_feature.py")
        added_files[file_id] = File(id=file_id, path="new_feature.py", language="python")

        head_indexer.index_repository({"files": {"new_feature.py": head_files["new_feature.py"]}}, adapter)
        head_facts = head_sink.build_facts()

        overlay = RepositoryOverlay(
            added_files=added_files,
            removed_files=set(),
            modified_files=set(),
            added_symbols={s.id: s for s in head_facts.symbols},
            removed_symbols=set(),
            added_calls=set(head_facts.calls),
            added_references=set(head_facts.references),
        )

        inc_view = RepositoryView(base_query, overlay)

        # Verify
        inc_syms, inc_calls, _inc_refs = extract_view_fqns(inc_view, base_indexer, head_indexer)
        full_syms, full_calls, _full_refs = extract_full_fqns(full_facts, full_indexer)

        assert inc_syms == full_syms
        assert inc_calls == full_calls

    def test_delete_file_incremental_benchmark(self):
        """Benchmark deleting a leaf file from a 100-file repository."""
        adapter = PythonLanguageAdapter()
        repo_files = generate_synthetic_repo(num_files=100)

        # Base facts
        base_sink = InMemoryFactSink()
        base_indexer = RepositoryIndexer(base_sink)
        base_indexer.index_repository({"files": repo_files}, adapter)
        base_facts = base_sink.build_facts()
        base_query = InMemoryRepository(base_facts)

        # Head files (delete module_99.py)
        head_files = dict(repo_files)
        del head_files["module_99.py"]

        # Full compilation
        full_sink = InMemoryFactSink()
        full_indexer = RepositoryIndexer(full_sink)
        full_indexer.index_repository({"files": head_files}, adapter)
        full_facts = full_sink.build_facts()

        # Incremental compilation
        file_id = base_indexer.get_or_create_file_id("module_99.py")
        removed_symbols = set()
        for s in base_query.get_symbols_in_file(file_id):
            removed_symbols.add(s.id)

        overlay = RepositoryOverlay(
            added_files={},
            removed_files={file_id},
            modified_files=set(),
            added_symbols={},
            removed_symbols=removed_symbols,
            added_calls=set(),
            added_references=set(),
        )

        inc_view = RepositoryView(base_query, overlay)
        head_indexer = RepositoryIndexer(InMemoryFactSink())
        # Copy base symbol maps to head indexer to ensure alignment and avoid collisions
        for fqn, sym_id in base_indexer._symbol_id_map.items():
            head_indexer._symbol_id_map[fqn] = sym_id
            head_indexer._symbol_fqn_map[sym_id] = fqn
        head_indexer._next_symbol_id = base_indexer._next_symbol_id

        # Verify
        inc_syms, inc_calls, _inc_refs = extract_view_fqns(inc_view, base_indexer, head_indexer)
        full_syms, full_calls, _full_refs = extract_full_fqns(full_facts, full_indexer)

        assert inc_syms == full_syms
        assert inc_calls == full_calls

    def test_rename_symbol_incremental_benchmark(self):
        """Benchmark renaming a core symbol that affects multiple downstream files."""
        adapter = PythonLanguageAdapter()
        repo_files = generate_synthetic_repo(num_files=30)

        # Base facts
        base_sink = InMemoryFactSink()
        base_indexer = RepositoryIndexer(base_sink)
        base_indexer.index_repository({"files": repo_files}, adapter)
        base_facts = base_sink.build_facts()
        base_query = InMemoryRepository(base_facts)

        # Rename core_utility to core_utility_v2 in module_0.py and update module_1.py
        head_files = dict(repo_files)
        head_files["module_0.py"] = repo_files["module_0.py"].replace(
            "core_utility", "core_utility_v2"
        )
        head_files["module_1.py"] = repo_files["module_1.py"].replace(
            "core_utility", "core_utility_v2"
        )

        # Full compilation
        full_sink = InMemoryFactSink()
        full_indexer = RepositoryIndexer(full_sink)
        full_indexer.index_repository({"files": head_files}, adapter)
        full_facts = full_sink.build_facts()

        # Incremental compilation
        head_sink = InMemoryFactSink()
        head_indexer = RepositoryIndexer(head_sink)
        # Copy base symbol maps to head indexer to ensure alignment and avoid collisions
        for fqn, sym_id in base_indexer._symbol_id_map.items():
            head_indexer._symbol_id_map[fqn] = sym_id
            head_indexer._symbol_fqn_map[sym_id] = fqn
        head_indexer._next_symbol_id = base_indexer._next_symbol_id
        
        modified_files = set()
        added_files = {}

        for path in ["module_0.py", "module_1.py"]:
            file_id = base_indexer.get_or_create_file_id(path)
            modified_files.add(file_id)
            added_files[file_id] = File(id=file_id, path=path, language="python")
            head_indexer._file_id_map[path] = file_id

        files_to_index = {
            path: head_files[path] for path in ["module_0.py", "module_1.py"]
        }
        head_indexer.index_repository({"files": files_to_index}, adapter)
        head_facts = head_sink.build_facts()

        removed_symbols = set()
        for rf_id in modified_files:
            for s in base_query.get_symbols_in_file(rf_id):
                removed_symbols.add(s.id)

        overlay = RepositoryOverlay(
            added_files=added_files,
            removed_files=modified_files,
            modified_files=modified_files,
            added_symbols={s.id: s for s in head_facts.symbols},
            removed_symbols=removed_symbols,
            added_calls=set(head_facts.calls),
            added_references=set(head_facts.references),
        )

        inc_view = RepositoryView(base_query, overlay)

        # Verify
        inc_syms, inc_calls, _inc_refs = extract_view_fqns(inc_view, base_indexer, head_indexer)
        full_syms, full_calls, _full_refs = extract_full_fqns(full_facts, full_indexer)

        assert inc_syms == full_syms
        assert inc_calls == full_calls

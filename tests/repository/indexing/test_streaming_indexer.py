import gc
import weakref

import pytest

from engine.language.python.adapter import PythonLanguageAdapter
from engine.repository.indexing import (
    FactsToIndexAdapter,
    InMemoryFactSink,
    RepositoryIndexer,
)


@pytest.fixture
def test_files():
    return {
        "app.py": """
def main():
    helper()
""",
        "helper.py": """
def helper():
    pass
""",
    }


def test_streaming_contract_ast_release(test_files):
    """
    Test the strict streaming invariant:
    For every file:
    1. Load source
    2. Parse/index
    3. Extract facts
    4. Write facts
    5. Release AST
    6. Continue

    Ensure that FileIndex/AST objects are NOT retained in memory by the indexer
    after each file is indexed. We use weakref to assert garbage collection.
    """
    sink = InMemoryFactSink()
    indexer = RepositoryIndexer(sink)
    adapter = PythonLanguageAdapter()

    # Store weak references to the FileIndex objects produced during streaming
    weak_refs = []

    # Wrap _index_single_file to capture the returned FileIndex object
    original_index_single = adapter._index_single_file

    def wrapped_index_single(file_path, content, language):
        f_idx = original_index_single(file_path, content, language)
        weak_refs.append(weakref.ref(f_idx))
        return f_idx

    adapter._index_single_file = wrapped_index_single

    # Run the indexer
    indexer.index_repository({"files": test_files}, adapter)

    # Clean up and trigger GC to reclaim released objects
    gc.collect()

    # Assert that all parsed FileIndex/AST references have been released (i.e. weakref points to None)
    for ref in weak_refs:
        assert ref() is None, "A FileIndex/AST object was retained in memory!"


def test_fact_count_and_relationship_equivalence(test_files):
    """
    Test fact-count and relationship equivalence against the old implementation.
    The new RepositoryIndexer + InMemoryFactSink + FactsToIndexAdapter must produce
    equivalent semantic models to the old compile pipeline.
    """
    # 1. Build index via old pipeline
    adapter = PythonLanguageAdapter()
    old_index = adapter.build_index({"files": test_files})

    # 2. Build index via new RepositoryIndexer + FactsToIndexAdapter
    sink = InMemoryFactSink()
    indexer = RepositoryIndexer(sink)
    indexer.index_repository({"files": test_files}, adapter)
    facts = sink.build_facts()

    adapter_compat = FactsToIndexAdapter(indexer)
    new_index = adapter_compat.convert(facts, "python")

    # Assert equivalent files count
    assert len(new_index.files) == len(old_index.files)

    # Find matching files
    old_files_map = {f.path: f for f in old_index.files}
    new_files_map = {f.path: f for f in new_index.files}

    for path in old_files_map:
        old_f = old_files_map[path]
        new_f = new_files_map[path]

        # Assert symbols equivalence
        assert len(new_f.symbols) == len(old_f.symbols)
        old_syms = {s.name: s for s in old_f.symbols}
        new_syms = {s.name: s for s in new_f.symbols}
        assert set(old_syms.keys()) == set(new_syms.keys())

        # Assert calls equivalence
        assert len(new_f.calls) == len(old_f.calls)
        old_calls = {(c.caller, c.callee) for c in old_f.calls}
        new_calls = {(c.caller, c.callee) for c in new_f.calls}
        assert old_calls == new_calls

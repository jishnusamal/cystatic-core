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

    for path, old_f in old_files_map.items():
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


def test_incremental_batch_equivalence():
    """
    Verify:
    index(A + B + C)
    produces equivalent facts to:
    index(A)
    index(B)
    index(C)
    where the same repository/version is involved.
    We test both InMemoryFactSink and PersistentFactSink (with SQLite store).
    """
    import os
    import tempfile

    from engine.repository.store.sink import PersistentFactSink
    from engine.repository.store.sqlite import SQLiteRepositoryStore

    test_files = {
        "module_a.py": """
def func_a():
    func_b()
""",
        "module_b.py": """
def func_b():
    func_c()
""",
        "module_c.py": """
def func_c():
    pass
""",
    }

    adapter = PythonLanguageAdapter()

    # --- Scenario 1: InMemoryFactSink ---
    # Case 1.1: Single batch indexing (A + B + C)
    sink_all = InMemoryFactSink()
    indexer_all = RepositoryIndexer(sink_all)
    indexer_all.index_files(test_files, adapter=adapter)
    facts_all = sink_all.build_facts()

    # Case 1.2: Sequential indexing with a NEW indexer instance per batch
    sink_diff = InMemoryFactSink()

    indexer_a = RepositoryIndexer(sink_diff)
    indexer_a.index_files({"module_a.py": test_files["module_a.py"]}, adapter=adapter)

    indexer_b = RepositoryIndexer(sink_diff)
    indexer_b.index_files({"module_b.py": test_files["module_b.py"]}, adapter=adapter)

    indexer_c = RepositoryIndexer(sink_diff)
    indexer_c.index_files({"module_c.py": test_files["module_c.py"]}, adapter=adapter)

    facts_diff = sink_diff.build_facts()

    # Verify equivalence of InMemoryFactSink facts
    assert len(facts_all.files) == len(facts_diff.files)
    assert len(facts_all.symbols) == len(facts_diff.symbols)
    assert len(facts_all.calls) == len(facts_diff.calls)

    files_all_paths = {f.path for f in facts_all.files}
    files_diff_paths = {f.path for f in facts_diff.files}
    assert files_all_paths == files_diff_paths

    symbols_all_names = {s.name for s in facts_all.symbols}
    symbols_diff_names = {s.name for s in facts_diff.symbols}
    assert symbols_all_names == symbols_diff_names

    # --- Scenario 2: PersistentFactSink (SQLite Store) ---
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_store.db")

        # Case 2.1: Single batch indexing (A + B + C)
        store_all = SQLiteRepositoryStore(db_path)
        repo_id_all = store_all.create_repository("github", "owner", "repo_all")
        version_id_all = store_all.create_version(repo_id_all, "commit1")
        store_all.set_version_context(repo_id_all, version_id_all)

        sink_db_all = PersistentFactSink(store_all, repo_id_all, version_id_all)
        indexer_db_all = RepositoryIndexer(sink_db_all)
        indexer_db_all.index_files(test_files, adapter=adapter)
        sink_db_all.flush()

        # Fetch facts from SQLite
        cur_all = store_all.conn.cursor()
        cur_all.execute(
            "SELECT path, language FROM files WHERE repository_id = ? AND version_id = ? ORDER BY path",
            (repo_id_all, version_id_all),
        )
        files_all = [(row["path"], row["language"]) for row in cur_all.fetchall()]

        cur_all.execute(
            "SELECT name, kind, language FROM symbols WHERE repository_id = ? AND version_id = ? ORDER BY name, kind",
            (repo_id_all, version_id_all),
        )
        symbols_all = [(row["name"], row["kind"], row["language"]) for row in cur_all.fetchall()]

        # Case 2.2: Sequential indexing with a NEW indexer instance per batch
        store_seq = SQLiteRepositoryStore(db_path)
        repo_id_seq = store_seq.create_repository("github", "owner", "repo_seq")
        version_id_seq = store_seq.create_version(repo_id_seq, "commit1")
        store_seq.set_version_context(repo_id_seq, version_id_seq)

        sink_db_seq = PersistentFactSink(store_seq, repo_id_seq, version_id_seq)

        indexer_db_a = RepositoryIndexer(sink_db_seq)
        indexer_db_a.index_files({"module_a.py": test_files["module_a.py"]}, adapter=adapter)
        sink_db_seq.flush()

        indexer_db_b = RepositoryIndexer(sink_db_seq)
        indexer_db_b.index_files({"module_b.py": test_files["module_b.py"]}, adapter=adapter)
        sink_db_seq.flush()

        indexer_db_c = RepositoryIndexer(sink_db_seq)
        indexer_db_c.index_files({"module_c.py": test_files["module_c.py"]}, adapter=adapter)
        sink_db_seq.flush()

        # Fetch facts from SQLite for sequential run
        cur_seq = store_seq.conn.cursor()
        cur_seq.execute(
            "SELECT path, language FROM files WHERE repository_id = ? AND version_id = ? ORDER BY path",
            (repo_id_seq, version_id_seq),
        )
        files_seq = [(row["path"], row["language"]) for row in cur_seq.fetchall()]

        cur_seq.execute(
            "SELECT name, kind, language FROM symbols WHERE repository_id = ? AND version_id = ? ORDER BY name, kind",
            (repo_id_seq, version_id_seq),
        )
        symbols_seq = [(row["name"], row["kind"], row["language"]) for row in cur_seq.fetchall()]

        # Verify equivalence
        assert files_all == files_seq
        assert symbols_all == symbols_seq

import hashlib
import sqlite3
from engine.repository.facts import (
    Call,
    CallType,
    File,
    FileId,
    Import,
    ImportType,
    Reference,
    ReferenceType,
    Symbol,
    SymbolId,
    SymbolKind,
    SymbolVisibility,
)
from engine.repository.store import SQLiteRepositoryStore
from engine.repository.store.sink import PersistentFactSink
from engine.repository.indexing.indexer import RepositoryIndexer
from engine.repository.metrics import RepositoryMaterializationMetrics


def test_partial_store_metadata_recording():
    store = SQLiteRepositoryStore(":memory:")
    repo_id = store.create_repository("github", "testowner", "testrepo")
    version_id = store.create_version(repo_id, "commit1")
    commit_sha = "commit1"

    # Record tree
    tree = [
        {"path": "a.py", "size": 100, "blob_sha": "sha_a"},
        {"path": "b.py", "size": 200, "blob_sha": "sha_b"},
    ]
    store.record_tree(repo_id, commit_sha, tree)

    # Check is_materialized before indexing
    assert not store.is_materialized(repo_id, commit_sha, "a.py")
    
    # Record materializations
    store.record_materialization(repo_id, commit_sha, "a.py", "sha_a", "indexed")
    store.record_materialization(repo_id, commit_sha, "b.py", "sha_b", "pending")
    
    # Coverage / Stats check
    stats = store.get_materialization_stats(repo_id, commit_sha)
    assert stats.total_files == 2
    assert stats.indexed_files == 1
    assert stats.failed_files == 0
    assert stats.pending_files == 1

    coverage = store.get_materialization_coverage(repo_id, commit_sha)
    assert coverage.known_files == 2
    assert coverage.materialized_files == 1
    assert coverage.known_bytes == 300
    assert coverage.materialized_bytes == 100

    # Individual record checking
    record = store.get_materialization(repo_id, commit_sha, "a.py")
    assert record is not None
    assert record.indexed_status == "indexed"
    assert record.blob_sha == "sha_a"

    paths = store.get_materialized_paths(repo_id, commit_sha)
    assert "a.py" in paths
    assert "b.py" not in paths

    # Set indexed complete
    assert store.is_materialized(repo_id, commit_sha, "a.py")
    store.set_indexed_complete(repo_id, commit_sha, indexed_complete=True)
    assert store.is_materialized(repo_id, commit_sha, "a.py")


def test_partial_store_query_completeness():
    store = SQLiteRepositoryStore(":memory:")
    repo_id = store.create_repository("github", "testowner", "testrepo")
    version_id = store.create_version(repo_id, "commit1")
    commit_sha = "commit1"
    store.set_version_context(repo_id, version_id)

    # Incomplete repository query
    assert not store.is_materialized(repo_id, commit_sha, "test.py")

    sink = PersistentFactSink(store, repo_id, version_id)
    file_fact = File(id=FileId(1), path="test.py", language="python")
    sink.add_file(file_fact)

    sym = Symbol(
        id=SymbolId(10),
        name="func",
        file_id=file_fact.id,
        kind=SymbolKind.FUNCTION,
        language="python",
        start_line=1,
        end_line=10,
        visibility=SymbolVisibility.PUBLIC,
        parent_symbol_id=None,
    )
    sink.add_symbol(sym)
    sink.flush()

    # Query without files indexed -> complete = False
    symbols_res = store.get_symbols_in_file(file_fact.id)
    assert not symbols_res.complete

    # Mark the file materialized
    store.record_materialization(repo_id, commit_sha, "test.py", "sha_test", "indexed")

    # Now file queries should be complete!
    symbols_res = store.get_symbols_in_file(file_fact.id)
    assert symbols_res.complete
    assert len(symbols_res) == 1
    assert symbols_res.facts[0].name == "func"

    # Repository wide query is still incomplete
    callers_res = store.get_callers(SymbolId(10))
    assert not callers_res.complete

    # Mark repository indexing complete
    store.set_indexed_complete(repo_id, commit_sha, indexed_complete=True)
    callers_res = store.get_callers(SymbolId(10))
    assert callers_res.complete


def test_blob_fact_cache_reuse():
    store = SQLiteRepositoryStore(":memory:")
    repo_id = store.create_repository("github", "testowner", "testrepo")
    version_id = store.create_version(repo_id, "commit1")
    store.set_version_context(repo_id, version_id)

    # Perform indexing
    indexer = RepositoryIndexer(PersistentFactSink(store, repo_id, version_id))
    metrics = RepositoryMaterializationMetrics()

    files = {
        "a.py": "def foo():\n    pass\n",
    }
    indexer.index_files(files, language="python", metrics=metrics)

    # Verify first index was a cache miss
    assert metrics.blob_cache_misses == 1
    assert metrics.blob_cache_hits == 0
    assert metrics.facts_generated > 0

    # Index again with same content -> should hit cache!
    metrics2 = RepositoryMaterializationMetrics()
    version_id2 = store.create_version(repo_id, "commit2")
    store.set_version_context(repo_id, version_id2)
    
    indexer2 = RepositoryIndexer(PersistentFactSink(store, repo_id, version_id2))
    indexer2.index_files(files, language="python", metrics=metrics2)

    assert metrics2.blob_cache_misses == 0
    assert metrics2.blob_cache_hits == 1
    assert metrics2.facts_generated > 0

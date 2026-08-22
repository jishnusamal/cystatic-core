import pytest
from unittest.mock import MagicMock

from engine.repository.facts import (
    File, FileId, Symbol, SymbolId, Call, CallType, SymbolKind
)
from engine.repository.store import SQLiteRepositoryStore
from engine.repository.store.sink import PersistentFactSink
from engine.repository.indexing.indexer import RepositoryIndexer
from engine.repository.metrics import RepositoryMaterializationMetrics
from engine.repository.materialization.budget import MaterializationBudget
from engine.repository.materialization.materializer import RepositoryMaterializer
from engine.repository.overlay import RepositoryOverlay, RepositoryView

from engine.repository.materialization.request import MaterializationRequest
from engine.repository.resolver.resolver import RepositoryResolver
from engine.repository.resolver.requirements import (
    SymbolResolutionRequirement, FileResolutionRequirement
)
from tests.engine.repository.materialization.test_materializer import MockRepositoryProvider

@pytest.mark.asyncio
async def test_lazy_resolver_callees():
    # 1. Create SQLite store
    store = SQLiteRepositoryStore(":memory:")
    repo_id = store.create_repository("github", "testowner", "testrepo")
    commit_sha = "commit1"
    version_id = store.create_version(repo_id, commit_sha)
    store.set_version_context(repo_id, version_id)

    # Record tree
    tree = [
        {"path": "caller.py", "size": 100, "blob_sha": "sha_caller", "type": "blob"},
        {"path": "callee.py", "size": 150, "blob_sha": "sha_callee", "type": "blob"},
    ]
    store.record_tree(repo_id, commit_sha, tree)

    # 2. Setup providers
    source = MockRepositoryProvider({
        "caller.py": (
            "sha_caller",
            b"from callee import target_func\ndef caller_func():\n    target_func()\n"
        ),
        "callee.py": (
            "sha_callee",
            b"def target_func():\n    pass\n"
        ),
    })

    sink = PersistentFactSink(store, repo_id, version_id)
    indexer = RepositoryIndexer(sink)
    budget = MaterializationBudget(max_files=10, max_bytes=10000, max_remote_requests=5)
    metrics = RepositoryMaterializationMetrics()
    materializer = RepositoryMaterializer(source, store, indexer, budget, metrics)

    # 3. Create Resolver
    resolver = RepositoryResolver(store, source, materializer)

    # 4. Initially, callee.py is not materialized. Let's register a stub for target_func in DB.
    callee_file_id = indexer.get_or_create_file_id("callee.py")
    target_sym_id = indexer.get_or_create_symbol_id("python://callee.py::target_func")

    # Save target_func to DB without materializing callee.py
    cur = store.conn.cursor()
    cur.execute(
        "INSERT INTO symbols (repository_id, version_id, id, name, file_id, kind, language, start_line, end_line, visibility) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (repo_id, version_id, int(target_sym_id), "target_func", int(callee_file_id), "function", "python", 1, 5, "public")
    )
    cur.execute(
        "INSERT INTO files (repository_id, version_id, id, path, language, state) VALUES (?, ?, ?, ?, ?, ?)",
        (repo_id, version_id, int(callee_file_id), "callee.py", "python", "active")
    )
    store.conn.commit()

    assert not store.is_materialized(repo_id, commit_sha, "callee.py")

    # Create view
    overlay = RepositoryOverlay()
    view = RepositoryView(store, overlay, resolver=resolver)

    # Query callees
    callees_res = view.get_callees(target_sym_id)

    assert callees_res.complete
    assert store.is_materialized(repo_id, commit_sha, "callee.py")


@pytest.mark.asyncio
async def test_lazy_resolver_callers():
    store = SQLiteRepositoryStore(":memory:")
    repo_id = store.create_repository("github", "testowner", "testrepo")
    commit_sha = "commit1"
    version_id = store.create_version(repo_id, commit_sha)
    store.set_version_context(repo_id, version_id)

    tree = [
        {"path": "caller.py", "size": 100, "blob_sha": "sha_caller", "type": "blob"},
        {"path": "callee.py", "size": 150, "blob_sha": "sha_callee", "type": "blob"},
    ]
    store.record_tree(repo_id, commit_sha, tree)

    source = MockRepositoryProvider({
        "caller.py": (
            "sha_caller",
            b"from callee import target_func\ndef caller_func():\n    target_func()\n"
        ),
        "callee.py": (
            "sha_callee",
            b"def target_func():\n    pass\n"
        ),
    })

    sink = PersistentFactSink(store, repo_id, version_id)
    indexer = RepositoryIndexer(sink)
    budget = MaterializationBudget(max_files=10, max_bytes=10000, max_remote_requests=5)
    metrics = RepositoryMaterializationMetrics()
    materializer = RepositoryMaterializer(source, store, indexer, budget, metrics)

    resolver = RepositoryResolver(store, source, materializer)

    await materializer.materialize(
        MaterializationRequest(repo_id, commit_sha, ("callee.py",), "callee_init")
    )
    assert store.is_materialized(repo_id, commit_sha, "callee.py")
    assert not store.is_materialized(repo_id, commit_sha, "caller.py")

    target_sym_id = indexer.get_or_create_symbol_id("python://callee.py::target_func")

    # Create view
    overlay = RepositoryOverlay()
    view = RepositoryView(store, overlay, resolver=resolver)

    # Query callers
    callers_res = view.get_callers(target_sym_id)

    cur = store.conn.cursor()
    cur.execute("SELECT * FROM symbols")
    print("SYMBOLS IN DB:", [dict(r) for r in cur.fetchall()])
    cur.execute("SELECT * FROM calls")
    print("CALLS IN DB:", [dict(r) for r in cur.fetchall()])

    assert callers_res.complete
    assert len(callers_res.facts) == 1
    assert store.is_materialized(repo_id, commit_sha, "caller.py")

from unittest.mock import MagicMock

import pytest

from engine.repository.indexing.indexer import RepositoryIndexer
from engine.repository.materialization.budget import (
    MaterializationBudget,
    MaterializationBudgetExceeded,
)
from engine.repository.materialization.materializer import (
    RepositoryMaterializer,
    normalize_path,
)
from engine.repository.materialization.request import MaterializationRequest
from engine.repository.metrics import RepositoryMaterializationMetrics
from engine.repository.store import SQLiteRepositoryStore
from engine.repository.store.sink import PersistentFactSink
from integrations.base import RepositoryBlob, RepositoryProvider


class MockRepositoryProvider(RepositoryProvider):
    def __init__(self, files_dict=None):
        # files_dict: maps path -> (blob_sha, content_bytes)
        self.files_dict = files_dict or {}
        self.get_files_called_count = 0
        self.get_files_called_paths = []

    async def fetch_repository(self, repo_ref):
        return MagicMock()

    async def fetch_repository_at_sha(self, repo_ref, sha):
        return MagicMock()

    async def fetch_diff(self, repo_ref, base_sha, head_sha):
        return MagicMock()

    async def fetch_file(self, repo_ref, file_path, sha):
        return ""

    async def fetch_tree(self, repo_ref, sha):
        return {}

    async def fetch_commit(self, repo_ref, sha):
        return {}

    async def get_commit(self, repository, sha):
        from integrations.base import RepositoryCommit
        return RepositoryCommit(sha=sha, repository=repository)

    async def get_tree(self, repository, sha):
        return []

    async def get_file(self, repository, path, ref):
        return MagicMock()

    async def get_files(self, repository, paths, ref):
        self.get_files_called_count += 1
        self.get_files_called_paths.append(list(paths))
        res = []
        for p in paths:
            if p in self.files_dict:
                sha, content = self.files_dict[p]
                res.append(RepositoryBlob(path=p, sha=sha, size=len(content), content=content))
        return res


def test_path_normalization():
    assert normalize_path("a.py") == "a.py"
    assert normalize_path("./b.py") == "b.py"
    assert normalize_path("a/b/../c.py") == "a/c.py"
    assert normalize_path("a\\b\\c.py") == "a/b/c.py"
    assert normalize_path("") == ""


@pytest.mark.asyncio
async def test_basic_materialization():
    store = SQLiteRepositoryStore(":memory:")
    repo_id = store.create_repository("github", "testowner", "testrepo")
    commit_sha = "commit1"
    version_id = store.create_version(repo_id, commit_sha)
    store.set_version_context(repo_id, version_id)

    # Record tree
    tree = [
        {"path": "a.py", "size": 100, "blob_sha": "sha_a", "type": "blob"},
        {"path": "b.py", "size": 200, "blob_sha": "sha_b", "type": "blob"},
        {"path": "c.py", "size": 300, "blob_sha": "sha_c", "type": "blob"},
    ]
    store.record_tree(repo_id, commit_sha, tree)

    source = MockRepositoryProvider({
        "a.py": ("sha_a", b"def foo():\n    pass\n"),
        "b.py": ("sha_b", b"def bar():\n    pass\n"),
        "c.py": ("sha_c", b"def baz():\n    pass\n"),
    })

    sink = PersistentFactSink(store, repo_id, version_id)
    indexer = RepositoryIndexer(sink)
    budget = MaterializationBudget(max_files=10, max_bytes=10000, max_remote_requests=5)
    metrics = RepositoryMaterializationMetrics()

    materializer = RepositoryMaterializer(source, store, indexer, budget, metrics)

    request = MaterializationRequest(
        repository_id=repo_id,
        commit_sha=commit_sha,
        paths=("a.py", "b.py", "c.py"),
        reason="caller_resolution",
    )

    result = await materializer.materialize(request)

    assert len(result.materialized_paths) == 3
    assert "a.py" in result.materialized_paths
    assert "b.py" in result.materialized_paths
    assert "c.py" in result.materialized_paths
    assert len(result.already_materialized_paths) == 0
    assert len(result.failed_paths) == 0

    assert store.is_materialized(repo_id, commit_sha, "a.py")
    assert store.is_materialized(repo_id, commit_sha, "b.py")
    assert store.is_materialized(repo_id, commit_sha, "c.py")

    assert source.get_files_called_count == 1
    assert sorted(source.get_files_called_paths[0]) == ["a.py", "b.py", "c.py"]


@pytest.mark.asyncio
async def test_deduplication():
    store = SQLiteRepositoryStore(":memory:")
    repo_id = store.create_repository("github", "testowner", "testrepo")
    commit_sha = "commit1"
    version_id = store.create_version(repo_id, commit_sha)
    store.set_version_context(repo_id, version_id)

    # Record tree
    tree = [
        {"path": "a.py", "size": 100, "blob_sha": "sha_a", "type": "blob"},
        {"path": "b.py", "size": 200, "blob_sha": "sha_b", "type": "blob"},
    ]
    store.record_tree(repo_id, commit_sha, tree)

    source = MockRepositoryProvider({
        "a.py": ("sha_a", b"pass"),
        "b.py": ("sha_b", b"pass"),
    })

    sink = PersistentFactSink(store, repo_id, version_id)
    indexer = RepositoryIndexer(sink)
    budget = MaterializationBudget(max_files=10, max_bytes=10000, max_remote_requests=5)
    metrics = RepositoryMaterializationMetrics()

    materializer = RepositoryMaterializer(source, store, indexer, budget, metrics)

    request = MaterializationRequest(
        repository_id=repo_id,
        commit_sha=commit_sha,
        paths=("a.py", "b.py", "a.py", "./b.py"),
        reason="caller_resolution",
    )

    result = await materializer.materialize(request)
    assert len(result.materialized_paths) == 2
    assert "a.py" in result.materialized_paths
    assert "b.py" in result.materialized_paths
    assert source.get_files_called_count == 1
    assert sorted(source.get_files_called_paths[0]) == ["a.py", "b.py"]


@pytest.mark.asyncio
async def test_already_materialized():
    store = SQLiteRepositoryStore(":memory:")
    repo_id = store.create_repository("github", "testowner", "testrepo")
    commit_sha = "commit1"
    version_id = store.create_version(repo_id, commit_sha)
    store.set_version_context(repo_id, version_id)

    # Record tree
    tree = [
        {"path": "a.py", "size": 100, "blob_sha": "sha_a", "type": "blob"},
        {"path": "b.py", "size": 200, "blob_sha": "sha_b", "type": "blob"},
        {"path": "c.py", "size": 300, "blob_sha": "sha_c", "type": "blob"},
    ]
    store.record_tree(repo_id, commit_sha, tree)

    # Pre-index a.py and b.py
    store.record_materialization(repo_id, commit_sha, "a.py", "sha_a", "indexed")
    store.record_materialization(repo_id, commit_sha, "b.py", "sha_b", "indexed")

    source = MockRepositoryProvider({
        "c.py": ("sha_c", b"def baz():\n    pass\n"),
    })

    sink = PersistentFactSink(store, repo_id, version_id)
    indexer = RepositoryIndexer(sink)
    budget = MaterializationBudget(max_files=10, max_bytes=10000, max_remote_requests=5)
    metrics = RepositoryMaterializationMetrics()

    materializer = RepositoryMaterializer(source, store, indexer, budget, metrics)

    request = MaterializationRequest(
        repository_id=repo_id,
        commit_sha=commit_sha,
        paths=("a.py", "b.py", "c.py"),
        reason="import_resolution",
    )

    result = await materializer.materialize(request)

    assert len(result.already_materialized_paths) == 2
    assert "a.py" in result.already_materialized_paths
    assert "b.py" in result.already_materialized_paths
    assert result.materialized_paths == ("c.py",)

    assert source.get_files_called_count == 1
    assert source.get_files_called_paths[0] == ["c.py"]


@pytest.mark.asyncio
async def test_blob_reuse_and_changed_blob():
    store = SQLiteRepositoryStore(":memory:")
    repo_id = store.create_repository("github", "testowner", "testrepo")
    
    commit_a = "commit_a"
    version_a = store.create_version(repo_id, commit_a)
    store.set_version_context(repo_id, version_a)
    
    # Record tree for commit_a
    tree_a = [{"path": "foo.py", "size": 100, "blob_sha": "sha_x", "type": "blob"}]
    store.record_tree(repo_id, commit_a, tree_a)

    source_a = MockRepositoryProvider({
        "foo.py": ("sha_x", b"def foo():\n    pass\n"),
    })
    
    sink_a = PersistentFactSink(store, repo_id, version_a)
    indexer_a = RepositoryIndexer(sink_a)
    budget = MaterializationBudget(max_files=10, max_bytes=10000, max_remote_requests=5)
    metrics_a = RepositoryMaterializationMetrics()

    mat_a = RepositoryMaterializer(source_a, store, indexer_a, budget, metrics_a)
    res_a = await mat_a.materialize(MaterializationRequest(repo_id, commit_a, ("foo.py",), "test"))
    
    assert res_a.materialized_paths == ("foo.py",)
    assert metrics_a.blob_cache_misses == 1
    assert metrics_a.blob_cache_hits == 0

    # 1. Test blob reuse for same blob in different commit
    commit_b = "commit_b"
    version_b = store.create_version(repo_id, commit_b)
    store.set_version_context(repo_id, version_b)
    
    # Same blob_sha "sha_x" for commit_b
    tree_b = [{"path": "foo.py", "size": 100, "blob_sha": "sha_x", "type": "blob"}]
    store.record_tree(repo_id, commit_b, tree_b)

    source_b = MockRepositoryProvider({
        "foo.py": ("sha_x", b"def foo():\n    pass\n"),
    })
    
    sink_b = PersistentFactSink(store, repo_id, version_b)
    indexer_b = RepositoryIndexer(sink_b)
    metrics_b = RepositoryMaterializationMetrics()

    mat_b = RepositoryMaterializer(source_b, store, indexer_b, budget, metrics_b)
    res_b = await mat_b.materialize(MaterializationRequest(repo_id, commit_b, ("foo.py",), "test"))

    assert res_b.materialized_paths == ("foo.py",)
    assert metrics_b.blob_cache_hits == 1
    assert metrics_b.blob_cache_misses == 0

    # 2. Test changed blob (new blob_sha "sha_y" for commit_c)
    commit_c = "commit_c"
    version_c = store.create_version(repo_id, commit_c)
    store.set_version_context(repo_id, version_c)
    
    tree_c = [{"path": "foo.py", "size": 100, "blob_sha": "sha_y", "type": "blob"}]
    store.record_tree(repo_id, commit_c, tree_c)

    source_c = MockRepositoryProvider({
        "foo.py": ("sha_y", b"def foo_updated():\n    pass\n"),
    })
    
    sink_c = PersistentFactSink(store, repo_id, version_c)
    indexer_c = RepositoryIndexer(sink_c)
    metrics_c = RepositoryMaterializationMetrics()

    mat_c = RepositoryMaterializer(source_c, store, indexer_c, budget, metrics_c)
    res_c = await mat_c.materialize(MaterializationRequest(repo_id, commit_c, ("foo.py",), "test"))

    assert res_c.materialized_paths == ("foo.py",)
    assert metrics_c.blob_cache_hits == 0
    assert metrics_c.blob_cache_misses == 1


@pytest.mark.asyncio
async def test_budget_enforcement():
    store = SQLiteRepositoryStore(":memory:")
    repo_id = store.create_repository("github", "testowner", "testrepo")
    commit_sha = "commit1"
    version_id = store.create_version(repo_id, commit_sha)
    store.set_version_context(repo_id, version_id)

    # Record tree
    tree = [
        {"path": "a.py", "size": 100, "blob_sha": "sha_a", "type": "blob"},
        {"path": "b.py", "size": 200, "blob_sha": "sha_b", "type": "blob"},
    ]
    store.record_tree(repo_id, commit_sha, tree)

    source = MockRepositoryProvider({
        "a.py": ("sha_a", b"pass"),
        "b.py": ("sha_b", b"pass"),
    })

    sink = PersistentFactSink(store, repo_id, version_id)
    indexer = RepositoryIndexer(sink)
    metrics = RepositoryMaterializationMetrics()

    # Max files budget = 1
    budget_files = MaterializationBudget(max_files=1, max_bytes=10000, max_remote_requests=5)
    materializer_files = RepositoryMaterializer(source, store, indexer, budget_files, metrics)
    with pytest.raises(MaterializationBudgetExceeded) as exc_info:
        await materializer_files.materialize(MaterializationRequest(repo_id, commit_sha, ("a.py", "b.py"), "test"))
    assert "File budget exceeded" in str(exc_info.value)

    # Max bytes budget = 150
    budget_bytes = MaterializationBudget(max_files=10, max_bytes=150, max_remote_requests=5)
    materializer_bytes = RepositoryMaterializer(source, store, indexer, budget_bytes, metrics)
    with pytest.raises(MaterializationBudgetExceeded) as exc_info:
        await materializer_bytes.materialize(MaterializationRequest(repo_id, commit_sha, ("a.py", "b.py"), "test"))
    assert "Byte budget exceeded" in str(exc_info.value)

    # Max remote requests = 1, but we batch size = 1, so 2 files need 2 requests
    budget_reqs = MaterializationBudget(max_files=10, max_bytes=10000, max_remote_requests=1)
    materializer_reqs = RepositoryMaterializer(source, store, indexer, budget_reqs, metrics, materialization_batch_size=1)
    with pytest.raises(MaterializationBudgetExceeded) as exc_info:
        await materializer_reqs.materialize(MaterializationRequest(repo_id, commit_sha, ("a.py", "b.py"), "test"))
    assert "Remote request budget exceeded" in str(exc_info.value)


@pytest.mark.asyncio
async def test_persistence_after_every_batch():
    store = SQLiteRepositoryStore(":memory:")
    repo_id = store.create_repository("github", "testowner", "testrepo")
    commit_sha = "commit1"
    version_id = store.create_version(repo_id, commit_sha)
    store.set_version_context(repo_id, version_id)

    tree = [
        {"path": "a.py", "size": 100, "blob_sha": "sha_a", "type": "blob"},
        {"path": "b.py", "size": 200, "blob_sha": "sha_b", "type": "blob"},
    ]
    store.record_tree(repo_id, commit_sha, tree)

    source = MockRepositoryProvider({
        "a.py": ("sha_a", b"def foo():\n    pass\n"),
        "b.py": ("sha_b", b"def bar():\n    pass\n"),
    })

    sink = PersistentFactSink(store, repo_id, version_id)
    indexer = RepositoryIndexer(sink)
    budget = MaterializationBudget(max_files=10, max_bytes=10000, max_remote_requests=5)
    metrics = RepositoryMaterializationMetrics()

    # Set batch size to 1 to force 2 batches
    materializer = RepositoryMaterializer(source, store, indexer, budget, metrics, materialization_batch_size=1)

    # We patch materialize slightly or query store during execution if possible.
    # Alternatively, we can check that after indexing completes, files are in store.
    result = await materializer.materialize(MaterializationRequest(repo_id, commit_sha, ("a.py", "b.py"), "test"))
    assert len(result.materialized_paths) == 2
    assert store.is_materialized(repo_id, commit_sha, "a.py")
    assert store.is_materialized(repo_id, commit_sha, "b.py")


@pytest.mark.asyncio
async def test_partial_failure_semantics():
    store = SQLiteRepositoryStore(":memory:")
    repo_id = store.create_repository("github", "testowner", "testrepo")
    commit_sha = "commit1"
    version_id = store.create_version(repo_id, commit_sha)
    store.set_version_context(repo_id, version_id)

    tree = [
        {"path": "a.py", "size": 100, "blob_sha": "sha_a", "type": "blob"},
        {"path": "b.py", "size": 200, "blob_sha": "sha_b", "type": "blob"},
        {"path": "c.py", "size": 300, "blob_sha": "sha_c", "type": "blob"},
    ]
    store.record_tree(repo_id, commit_sha, tree)

    # b.py has invalid syntax which causes the Python parser adapter to raise an exception
    source = MockRepositoryProvider({
        "a.py": ("sha_a", b"def foo():\n    pass\n"),
        "b.py": ("sha_b", b"def bar(\n"),  # Invalid syntax!
        "c.py": ("sha_c", b"def baz():\n    pass\n"),
    })

    sink = PersistentFactSink(store, repo_id, version_id)
    indexer = RepositoryIndexer(sink)

    # Mock index_files to raise an exception for b.py to simulate indexing failure
    original_index_files = indexer.index_files
    def mock_index_files(files, **kwargs):
        if "b.py" in files:
            # Replicate the indexer failure recording and raise
            store.record_materialization(repo_id, commit_sha, "b.py", "sha_b", "failed")
            store.conn.commit()
            raise ValueError("Mock parsing error")
        return original_index_files(files, **kwargs)
    indexer.index_files = mock_index_files

    budget = MaterializationBudget(max_files=10, max_bytes=10000, max_remote_requests=5)
    metrics = RepositoryMaterializationMetrics()

    materializer = RepositoryMaterializer(source, store, indexer, budget, metrics)

    result = await materializer.materialize(MaterializationRequest(repo_id, commit_sha, ("a.py", "b.py", "c.py"), "test"))

    assert "a.py" in result.materialized_paths
    assert "c.py" in result.materialized_paths
    assert "b.py" in result.failed_paths

    assert store.is_materialized(repo_id, commit_sha, "a.py")
    assert store.is_materialized(repo_id, commit_sha, "c.py")
    
    # Verify b.py materialization record is marked as failed
    b_mat = store.get_materialization(repo_id, commit_sha, "b.py")
    assert b_mat is not None
    assert b_mat.indexed_status == "failed"


@pytest.mark.asyncio
async def test_not_found_validation():
    store = SQLiteRepositoryStore(":memory:")
    repo_id = store.create_repository("github", "testowner", "testrepo")
    commit_sha = "commit1"
    version_id = store.create_version(repo_id, commit_sha)
    store.set_version_context(repo_id, version_id)

    # Record tree with only a.py
    tree = [
        {"path": "a.py", "size": 100, "blob_sha": "sha_a", "type": "blob"},
    ]
    store.record_tree(repo_id, commit_sha, tree)

    source = MockRepositoryProvider({
        "a.py": ("sha_a", b"pass"),
    })

    sink = PersistentFactSink(store, repo_id, version_id)
    indexer = RepositoryIndexer(sink)
    budget = MaterializationBudget(max_files=10, max_bytes=10000, max_remote_requests=5)
    metrics = RepositoryMaterializationMetrics()

    materializer = RepositoryMaterializer(source, store, indexer, budget, metrics)

    # Request includes missing.py which is not in the tree
    result = await materializer.materialize(MaterializationRequest(repo_id, commit_sha, ("a.py", "missing.py"), "test"))

    assert "a.py" in result.materialized_paths
    assert "missing.py" in result.failed_paths

    # Should not make request to remote for missing.py
    assert source.get_files_called_count == 1
    assert source.get_files_called_paths[0] == ["a.py"]

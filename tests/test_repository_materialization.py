"""Tests for classification-aware repository materialization.

Verifies that files excluded by the file-role analysis policy (frontend
TS/TSX, generated files) are never fetched from the remote provider, do not
consume materialization budget, and are represented explicitly (excluded ≠
missing ≠ failed).
"""

import pytest
from unittest.mock import MagicMock

from engine.repository.store import SQLiteRepositoryStore
from engine.repository.store.sink import PersistentFactSink
from engine.repository.indexing.indexer import RepositoryIndexer
from engine.repository.metrics import RepositoryMaterializationMetrics
from integrations.base import RepositoryProvider, RepositoryBlob

from engine.repository.materialization.budget import MaterializationBudget
from engine.repository.materialization.request import MaterializationRequest
from engine.repository.materialization.materializer import (
    MaterializationResult,
    RepositoryMaterializer,
)


class MockRepositoryProvider(RepositoryProvider):
    def __init__(self, files_dict=None):
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
                res.append(
                    RepositoryBlob(path=p, sha=sha, size=len(content), content=content)
                )
        return res


@pytest.fixture
def materializer_env():
    """Build a store + provider + materializer with a mixed frontend/backend tree."""

    def factory(
        files: dict[str, tuple[str, bytes]],
        tree: list[dict] | None = None,
        batch_size: int = 100,
        max_files: int = 10,
        max_bytes: int = 100_000,
    ):
        store = SQLiteRepositoryStore(":memory:")
        repo_id = store.create_repository("github", "owner", "repo")
        commit_sha = "commit1"
        version_id = store.create_version(repo_id, commit_sha)
        store.set_version_context(repo_id, version_id)

        recorded_tree = tree or [
            {"path": path, "size": len(content), "blob_sha": sha, "type": "blob"}
            for path, (sha, content) in files.items()
        ]
        store.record_tree(repo_id, commit_sha, recorded_tree)

        source = MockRepositoryProvider(files)
        sink = PersistentFactSink(store, repo_id, version_id)
        indexer = RepositoryIndexer(sink)
        budget = MaterializationBudget(
            max_files=max_files, max_bytes=max_bytes, max_remote_requests=5
        )
        metrics = RepositoryMaterializationMetrics()
        materializer = RepositoryMaterializer(
            source,
            store,
            indexer,
            budget,
            metrics,
            materialization_batch_size=batch_size,
        )
        return store, source, materializer, metrics, repo_id, commit_sha

    return factory


class TestExcludedFilesAreNotFetched:
    @pytest.mark.asyncio
    async def test_frontend_tsx_not_remotely_fetched(self, materializer_env):
        files = {
            "frontend/Button.tsx": ("sha_btn", b"export const Button = () => null;"),
            "backend/api.py": ("sha_api", b"def handler():\n    pass\n"),
            "shared/types.ts": ("sha_types", b"export interface User { id: string }"),
        }
        store, source, materializer, metrics, repo_id, commit_sha = materializer_env(files)

        result = await materializer.materialize(
            MaterializationRequest(
                repository_id=repo_id,
                commit_sha=commit_sha,
                paths=("frontend/Button.tsx", "backend/api.py", "shared/types.ts"),
                reason="test",
            )
        )

        # Frontend TSX excluded explicitly — not failed, not missing.
        assert result.excluded_paths == ("frontend/Button.tsx",)
        assert result.excluded_classifications == {"frontend/Button.tsx": "frontend"}
        assert "frontend/Button.tsx" not in result.failed_paths
        assert "frontend/Button.tsx" not in result.materialized_paths

        # Backend and shared still materialized.
        assert set(result.materialized_paths) == {"backend/api.py", "shared/types.ts"}

        # The remote provider was never asked for the excluded file.
        assert source.get_files_called_count == 1
        assert "frontend/Button.tsx" not in source.get_files_called_paths[0]

        # Not marked as indexed in the store either.
        assert not store.is_materialized(repo_id, commit_sha, "frontend/Button.tsx")

    @pytest.mark.asyncio
    async def test_exclusion_persisted_as_explicit_status(self, materializer_env):
        files = {
            "src/components/Card.tsx": ("sha_card", b"export const Card = () => null;"),
        }
        store, source, materializer, metrics, repo_id, commit_sha = materializer_env(files)

        result = await materializer.materialize(
            MaterializationRequest(repo_id, commit_sha, ("src/components/Card.tsx",), "t")
        )

        assert result.excluded_paths == ("src/components/Card.tsx",)
        record = store.get_materialization(repo_id, commit_sha, "src/components/Card.tsx")
        assert record is not None
        assert record.indexed_status == "excluded"

    @pytest.mark.asyncio
    async def test_generated_files_excluded_regardless_of_language(self, materializer_env):
        files = {
            "generated/schema_pb2.py": ("sha_pb2", b"# Generated code\n"),
            "server/main.py": ("sha_main", b"def main():\n    pass\n"),
        }
        store, source, materializer, metrics, repo_id, commit_sha = materializer_env(files)

        result = await materializer.materialize(
            MaterializationRequest(
                repo_id, commit_sha, ("generated/schema_pb2.py", "server/main.py"), "t"
            )
        )

        assert result.excluded_paths == ("generated/schema_pb2.py",)
        assert result.materialized_paths == ("server/main.py",)
        assert "generated/schema_pb2.py" not in source.get_files_called_paths[0]

    @pytest.mark.asyncio
    async def test_excluded_is_distinct_from_missing_and_failed(self, materializer_env):
        files = {
            "frontend/Page.tsx": ("sha_page", b"export default () => null;"),
            "services/core.py": ("sha_core", b"def run():\n    pass\n"),
        }
        tree = [
            {"path": "frontend/Page.tsx", "size": 26, "blob_sha": "sha_page", "type": "blob"},
            {"path": "services/core.py", "size": 22, "blob_sha": "sha_core", "type": "blob"},
            # missing.py intentionally absent from the tree
        ]
        store, source, materializer, metrics, repo_id, commit_sha = materializer_env(
            files, tree=tree
        )

        result = await materializer.materialize(
            MaterializationRequest(
                repo_id,
                commit_sha,
                ("frontend/Page.tsx", "services/core.py", "missing.py"),
                "t",
            )
        )

        assert result.excluded_paths == ("frontend/Page.tsx",)
        assert result.failed_paths == ("missing.py",)
        assert result.materialized_paths == ("services/core.py",)


class TestBudgetInteraction:
    @pytest.mark.asyncio
    async def test_excluded_file_does_not_consume_file_budget(self, materializer_env):
        # Budget allows only ONE file; two requested but one is excluded.
        files = {
            "frontend/Hero.tsx": ("sha_hero", b"export const Hero = () => null;"),
            "workers/job.py": ("sha_job", b"def job():\n    pass\n"),
        }
        store, source, materializer, metrics, repo_id, commit_sha = materializer_env(
            files, max_files=1
        )

        result = await materializer.materialize(
            MaterializationRequest(
                repo_id, commit_sha, ("frontend/Hero.tsx", "workers/job.py"), "t"
            )
        )

        assert result.materialized_paths == ("workers/job.py",)
        assert result.excluded_paths == ("frontend/Hero.tsx",)
        assert metrics.files_fetched == 1

    @pytest.mark.asyncio
    async def test_all_excluded_requests_fetch_nothing(self, materializer_env):
        files = {
            "web/App.jsx": ("sha_app", b"export default App;"),
            "__generated__/types.tsx": ("sha_gen", b"// generated"),
        }
        store, source, materializer, metrics, repo_id, commit_sha = materializer_env(files)

        result = await materializer.materialize(
            MaterializationRequest(
                repo_id, commit_sha, ("web/App.jsx", "__generated__/types.tsx"), "t"
            )
        )

        assert result.excluded_paths == ("__generated__/types.tsx", "web/App.jsx")
        assert result.materialized_paths == ()
        assert source.get_files_called_count == 0
        assert metrics.files_fetched == 0
        assert metrics.bytes_fetched == 0


class TestClassificationMetrics:
    @pytest.mark.asyncio
    async def test_metrics_count_eligible_excluded_and_kinds(self, materializer_env):
        files = {
            "frontend/A.tsx": ("sha_a", b"const a = 1;"),
            "pages/B.tsx": ("sha_b", b"const b = 2;"),
            "backend/api.ts": ("sha_c", b"export const api = {};"),
            "shared/types.ts": ("sha_d", b"export type X = 1;"),
            "unknown_util.ts": ("sha_e", b"export const u = 3;"),
        }
        store, source, materializer, metrics, repo_id, commit_sha = materializer_env(files)

        await materializer.materialize(
            MaterializationRequest(
                repo_id,
                commit_sha,
                (
                    "frontend/A.tsx",
                    "pages/B.tsx",
                    "backend/api.ts",
                    "shared/types.ts",
                    "unknown_util.ts",
                ),
                "t",
            )
        )

        snap = metrics.snapshot()
        assert snap["excluded_files"] == 2
        assert snap["excluded_frontend_files"] == 2
        assert snap["eligible_files"] == 3
        assert snap["classification_counts"]["frontend"] == 2
        assert snap["classification_counts"]["backend"] == 1
        assert snap["classification_counts"]["shared"] == 1
        assert snap["classification_counts"]["unknown"] == 1

    @pytest.mark.asyncio
    async def test_result_type_defaults_keep_backward_compatibility(self):
        result = MaterializationResult(
            requested_paths=("a.py",),
            materialized_paths=("a.py",),
            already_materialized_paths=(),
            failed_paths=(),
            bytes_fetched=10,
            facts_generated=1,
        )
        assert result.excluded_paths == ()
        assert result.excluded_classifications is None

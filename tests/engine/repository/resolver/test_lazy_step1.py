from unittest.mock import MagicMock

import pytest

from core.config import get_compiler_settings
from core.runtime import PREVENT_LEGACY_ARCHITECTURE
from engine.pipeline.pipeline import Pipeline
from engine.repository.store import SQLiteRepositoryStore
from integrations.base import (
    RepositoryBlob,
    RepositoryCommit,
    RepositoryProvider,
    RepositoryTreeEntry,
)
from models import (
    AnalysisRequest,
    AnalysisTrigger,
    DiffSnapshot,
    PullRequestReference,
    RepositoryReference,
)
from models.core import DiffFile, DiffHunk


class UnexpectedProviderCall(Exception):
    """Raised when a test mock provider method is invoked that should never be called."""


class MockLazyProvider(RepositoryProvider):
    def __init__(self, files_dict=None, tree_entries=None):
        self.files_dict = files_dict or {}
        self.tree_entries = tree_entries or []
        self.fetch_repository_called = False
        self.fetch_repository_at_sha_called = False
        self.get_files_called_count = 0
        self.get_files_called_paths = []

    async def fetch_repository(self, repo_ref):
        self.fetch_repository_called = True
        raise UnexpectedProviderCall("Should not call fetch_repository")

    async def fetch_repository_at_sha(self, repo_ref, sha):
        self.fetch_repository_at_sha_called = True
        raise UnexpectedProviderCall("Should not call fetch_repository_at_sha")

    async def fetch_diff(self, repo_ref, base_sha, head_sha):
        return MagicMock()

    async def fetch_file(self, repo_ref, file_path, sha):
        if file_path in self.files_dict:
            return self.files_dict[file_path][1].decode("utf-8")
        return ""

    async def fetch_tree(self, repo_ref, sha):
        return {}

    async def fetch_commit(self, repo_ref, sha):
        return {}

    async def get_commit(self, repository, sha):
        return RepositoryCommit(sha=sha, repository=repository)

    async def get_tree(self, repository, sha):
        return self.tree_entries

    async def get_file(self, repository, path, ref):
        if path in self.files_dict:
            sha, content = self.files_dict[path]
            return RepositoryBlob(path=path, sha=sha, size=len(content), content=content)
        raise UnexpectedProviderCall(f"File {path} not found")

    async def get_files(self, repository, paths, ref):
        self.get_files_called_count += 1
        self.get_files_called_paths.append(list(paths))
        res = []
        for p in paths:
            if p in self.files_dict:
                sha, content = self.files_dict[p]
                res.append(RepositoryBlob(path=p, sha=sha, size=len(content), content=content))
        return res

@pytest.mark.asyncio
async def test_lazy_step1_initialization():
    settings = get_compiler_settings()
    old_flag = settings.ENABLE_LAZY_REPOSITORY_RESOLUTION
    settings.ENABLE_LAZY_REPOSITORY_RESOLUTION = True

    try:
        store = SQLiteRepositoryStore(":memory:")
        base_sha = "base123"
        head_sha = "head123"

        # Base tree entries
        tree_entries = [
            RepositoryTreeEntry(path="a.py", type="blob", sha="sha_a", size=100),
            RepositoryTreeEntry(path="b.py", type="blob", sha="sha_b", size=200),
            RepositoryTreeEntry(path="c.py", type="blob", sha="sha_c", size=300),
        ]

        # Files dict (PR changed files)
        files_dict = {
            "a.py": ("sha_a_new", b"def func_a():\n    pass\n"),
        }

        provider = MockLazyProvider(files_dict=files_dict, tree_entries=tree_entries)
        pipeline = Pipeline(
            repository_store=store,
            repository_provider=provider,
        )

        repo_ref = RepositoryReference(
            provider="github",
            owner="testowner",
            repository="testrepo",
            default_branch=base_sha,
        )
        pr_ref = PullRequestReference(
            number=42,
            base_sha=base_sha,
            head_sha=head_sha,
            title="Lazy PR",
        )

        hunk = DiffHunk(
            file_path="a.py",
            source_start=1,
            source_length=2,
            target_start=1,
            target_length=2,
            added_lines=("+def func_a():", "+    pass"),
            removed_lines=(),
            lines=(),
        )
        diff_file = DiffFile(
            file_path="a.py",
            added_lines=("+def func_a():",),
            removed_lines=(),
            hunks=(hunk,),
        )
        diff_snapshot = DiffSnapshot(files=(diff_file,))

        request = AnalysisRequest(
            repository=repo_ref,
            pull_request=pr_ref,
            diff=diff_snapshot,
            trigger=AnalysisTrigger.MANUAL,
        )

        token = PREVENT_LEGACY_ARCHITECTURE.set(True)
        try:
            context = await pipeline.run(request)
        finally:
            PREVENT_LEGACY_ARCHITECTURE.reset(token)

        assert context.error is None
        assert not provider.fetch_repository_at_sha_called
        assert not provider.fetch_repository_called

        # Verify that b.py and c.py remained unmaterialized in base store
        cur = store.conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM repository_materialization WHERE repository_id = ? AND commit_sha = ? AND path IN ('b.py', 'c.py') AND indexed_status = 'indexed'",
            ("github/testowner/testrepo", base_sha)
        )
        base_unmaterialized_count = cur.fetchone()[0]
        assert base_unmaterialized_count == 0

        # Initial materialization ratio check
        metrics = context.repository_materialization
        assert metrics.repository_files == 3  # a.py, b.py, c.py
        
        # Check overlay
        assert context.repository_view is not None
        view = context.repository_view
        assert len(view.overlay.added_files) == 1
        assert len(view.overlay.removed_files) == 1

    finally:
        settings.ENABLE_LAZY_REPOSITORY_RESOLUTION = old_flag


@pytest.mark.asyncio
async def test_resolver_triggers_base_materialization_e2e():
    settings = get_compiler_settings()
    old_flag = settings.ENABLE_LAZY_REPOSITORY_RESOLUTION
    settings.ENABLE_LAZY_REPOSITORY_RESOLUTION = True

    try:
        store = SQLiteRepositoryStore(":memory:")
        base_sha = "base123"
        head_sha = "head123"

        # Base tree entries
        tree_entries = [
            RepositoryTreeEntry(path="a.py", type="blob", sha="sha_a", size=100),
            RepositoryTreeEntry(path="b.py", type="blob", sha="sha_b", size=200),
        ]

        # Files dict (PR changed files + base files requested lazily)
        files_dict = {
            "a.py": ("sha_a_new", b"from b import target_func\ndef func_a():\n    target_func()\n"),
            "b.py": ("sha_b", b"def target_func():\n    pass\n"),
        }

        provider = MockLazyProvider(files_dict=files_dict, tree_entries=tree_entries)
        pipeline = Pipeline(
            repository_store=store,
            repository_provider=provider,
        )

        repo_ref = RepositoryReference(
            provider="github",
            owner="testowner",
            repository="testrepo",
            default_branch=base_sha,
        )
        pr_ref = PullRequestReference(
            number=42,
            base_sha=base_sha,
            head_sha=head_sha,
            title="Lazy PR",
        )

        hunk = DiffHunk(
            file_path="a.py",
            source_start=1,
            source_length=3,
            target_start=1,
            target_length=3,
            added_lines=("+from b import target_func", "+def func_a():", "+    target_func()"),
            removed_lines=(),
            lines=(),
        )
        diff_file = DiffFile(
            file_path="a.py",
            added_lines=("+from b import target_func",),
            removed_lines=(),
            hunks=(hunk,),
        )
        diff_snapshot = DiffSnapshot(files=(diff_file,))

        request = AnalysisRequest(
            repository=repo_ref,
            pull_request=pr_ref,
            diff=diff_snapshot,
            trigger=AnalysisTrigger.MANUAL,
        )

        token = PREVENT_LEGACY_ARCHITECTURE.set(True)
        try:
            context = await pipeline.run(request)
        finally:
            PREVENT_LEGACY_ARCHITECTURE.reset(token)

        assert context.error is None
        view = context.repository_view
        assert view is not None

        # Verify b.py is NOT materialized initially
        assert not store.is_materialized("github/testowner/testrepo", base_sha, "b.py")

        # Now query symbols in file "b.py" to trigger resolution
        res = view.get_symbols_in_file("b.py")
        
        # Verify b.py has now been materialized
        assert store.is_materialized("github/testowner/testrepo", base_sha, "b.py")
        assert len(res.facts) == 1
        assert res.facts[0].name == "target_func"

    finally:
        settings.ENABLE_LAZY_REPOSITORY_RESOLUTION = old_flag

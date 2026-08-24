"""Phase 12 — Integration test: lazy→full equivalence (§18).

Tests the fallback flow end-to-end:
  1. The resolver signals budget_exhausted (mocked — the budget trigger unit
     tests are in test_fallback_triggers.py).
  2. FullIndexFallback.run() is called with the real RepositoryStore and
     RepositoryIndexer against a 5-file in-memory SQLite database.
  3. Asserts the resulting store state: indexed_complete=True, all files
     materialized, and RepositoryView refusing to re-enter the resolver.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from engine.repository.indexing.indexer import RepositoryIndexer
from engine.repository.materialization.budget import (
    BudgetExceededReason,
    ResolutionUsage,
)
from engine.repository.materialization.full_index import FullIndexFallback
from engine.repository.overlay import RepositoryOverlay, RepositoryView
from engine.repository.resolver.outcome import ResolutionOutcome
from engine.repository.resolver.requirements import FileResolutionRequirement
from engine.repository.store import SQLiteRepositoryStore
from engine.repository.store.sink import PersistentFactSink
from tests.engine.repository.materialization.test_materializer import (
    MockRepositoryProvider,
)

# ---------------------------------------------------------------------------
# Fixture: 5-file chain repository
# ---------------------------------------------------------------------------

CHAIN_FILES = {
    "a.py": ("sha_a", b"def func_a():\n    pass\n"),
    "b.py": ("sha_b", b"def func_b():\n    pass\n"),
    "c.py": ("sha_c", b"def func_c():\n    pass\n"),
    "d.py": ("sha_d", b"def func_d():\n    pass\n"),
    "e.py": ("sha_e", b"def func_e():\n    pass\n"),
}

TREE = [
    {"path": p, "size": len(content), "blob_sha": sha, "type": "blob"}
    for p, (sha, content) in CHAIN_FILES.items()
]


def _make_chain_store():
    store = SQLiteRepositoryStore(":memory:")
    repo_id = store.create_repository("github", "owner", "repo_chain")
    commit_sha = "chain_commit"
    version_id = store.create_version(repo_id, commit_sha)
    store.set_version_context(repo_id, version_id)
    store.record_tree(repo_id, commit_sha, TREE)
    return store, repo_id, commit_sha, version_id


def _make_source():
    return MockRepositoryProvider({
        p: (sha, content) for p, (sha, content) in CHAIN_FILES.items()
    })


def _make_view_with_mocked_exhausted_resolver(store, repo_id, commit_sha, version_id, source):
    """Wire RepositoryView so the resolver immediately returns budget_exhausted.

    The FullIndexFallback is real (backed by the same store + indexer).
    """
    sink = PersistentFactSink(store, repo_id, version_id)
    indexer = RepositoryIndexer(sink)

    # Mock resolver returns budget_exhausted unconditionally
    usage = ResolutionUsage(files=490, bytes=48 * 1024 * 1024)
    outcome = ResolutionOutcome.budget_exhausted(
        reason=BudgetExceededReason.MAX_FILES, rounds=1, usage=usage
    )
    mock_resolver = MagicMock()
    mock_resolver.resolve_sync.return_value = outcome

    fallback = FullIndexFallback(source=source, store=store, indexer=indexer)

    overlay = RepositoryOverlay()
    view = RepositoryView(
        store, overlay,
        resolver=mock_resolver,
        fallback=fallback,
        repository_id=repo_id,
        commit_sha=commit_sha,
    )
    return view, mock_resolver, fallback


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestLazyFullEquivalence:

    @patch("core.config.get_compiler_settings")
    def _run_path_b(self, mock_settings):
        mock_settings.return_value.ENABLE_LAZY_REPOSITORY_RESOLUTION = True
        store, repo_id, commit_sha, version_id = _make_chain_store()
        source = _make_source()
        view, mock_resolver, _fallback = _make_view_with_mocked_exhausted_resolver(
            store, repo_id, commit_sha, version_id, source
        )
        incomplete_result = MagicMock()
        incomplete_result.complete = False
        req = FileResolutionRequirement("a.py")
        view._resolve_if_needed(incomplete_result, req)
        return view, store, repo_id, commit_sha, mock_resolver

    def test_store_complete_after_fallback(self):
        with patch("core.config.get_compiler_settings") as mock_cs:
            mock_cs.return_value.ENABLE_LAZY_REPOSITORY_RESOLUTION = True
            store, repo_id, commit_sha, version_id = _make_chain_store()
            source = _make_source()
            view, _, _ = _make_view_with_mocked_exhausted_resolver(
                store, repo_id, commit_sha, version_id, source
            )
            req = FileResolutionRequirement("a.py")
            incomplete = MagicMock()
            incomplete.complete = False
            view._resolve_if_needed(incomplete, req)

        assert store._is_indexing_complete(), "store must be COMPLETE after FullIndexFallback"

    def test_all_files_materialized_after_fallback(self):
        with patch("core.config.get_compiler_settings") as mock_cs:
            mock_cs.return_value.ENABLE_LAZY_REPOSITORY_RESOLUTION = True
            store, repo_id, commit_sha, version_id = _make_chain_store()
            source = _make_source()
            view, _, _ = _make_view_with_mocked_exhausted_resolver(
                store, repo_id, commit_sha, version_id, source
            )
            req = FileResolutionRequirement("a.py")
            incomplete = MagicMock()
            incomplete.complete = False
            view._resolve_if_needed(incomplete, req)

        materialized = set(store.get_materialized_paths(repo_id, commit_sha))
        expected = set(CHAIN_FILES.keys())
        assert expected <= materialized, (
            f"Missing paths after fallback: {expected - materialized}"
        )

    def test_resolution_mode_is_full_after_successful_fallback(self):
        with patch("core.config.get_compiler_settings") as mock_cs:
            mock_cs.return_value.ENABLE_LAZY_REPOSITORY_RESOLUTION = True
            store, repo_id, commit_sha, version_id = _make_chain_store()
            source = _make_source()
            view, _, _ = _make_view_with_mocked_exhausted_resolver(
                store, repo_id, commit_sha, version_id, source
            )
            req = FileResolutionRequirement("a.py")
            incomplete = MagicMock()
            incomplete.complete = False
            view._resolve_if_needed(incomplete, req)

        assert view._resolution_mode == "FULL"
        assert view._last_fallback_result is not None
        assert view._last_fallback_result.success is True

    def test_is_store_complete_prevents_re_entry(self):
        """After fallback, _resolve_if_needed must return False without calling resolver."""
        with patch("core.config.get_compiler_settings") as mock_cs:
            mock_cs.return_value.ENABLE_LAZY_REPOSITORY_RESOLUTION = True
            store, repo_id, commit_sha, version_id = _make_chain_store()
            source = _make_source()
            view, mock_resolver, _ = _make_view_with_mocked_exhausted_resolver(
                store, repo_id, commit_sha, version_id, source
            )
            req = FileResolutionRequirement("a.py")
            incomplete = MagicMock()
            incomplete.complete = False
            view._resolve_if_needed(incomplete, req)

            # First call to resolve_sync happened above (budget exceeded → fallback)
            calls_after_first = mock_resolver.resolve_sync.call_count
            assert store._is_indexing_complete() is True

            # Second call should bail early — store is complete
            req2 = FileResolutionRequirement("e.py")
            result = view._resolve_if_needed(incomplete, req2)

        assert result is False, "_resolve_if_needed must return False when store is COMPLETE"
        assert mock_resolver.resolve_sync.call_count == calls_after_first, (
            "resolver.resolve_sync must not be called again after fallback"
        )

    def test_lazy_fallback_result_fields_populated(self):
        """FallbackResult fields must carry the lazy usage from the moment of budget exhaustion."""
        with patch("core.config.get_compiler_settings") as mock_cs:
            mock_cs.return_value.ENABLE_LAZY_REPOSITORY_RESOLUTION = True
            store, repo_id, commit_sha, version_id = _make_chain_store()
            source = _make_source()
            view, _, _ = _make_view_with_mocked_exhausted_resolver(
                store, repo_id, commit_sha, version_id, source
            )
            req = FileResolutionRequirement("a.py")
            incomplete = MagicMock()
            incomplete.complete = False
            view._resolve_if_needed(incomplete, req)

        result = view._last_fallback_result
        assert result is not None
        assert result.fallback_reason == BudgetExceededReason.MAX_FILES.value
        assert result.lazy_files_before == 490
        assert result.full_repository_files == len(CHAIN_FILES)

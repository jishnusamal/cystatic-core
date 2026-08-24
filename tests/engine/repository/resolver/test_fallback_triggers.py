"""Phase 12 — Unit tests for per-budget-threshold fallback triggering.

Tests §17: each budget limit (MAX_FILES, MAX_BYTES, MAX_REMOTE_REQUESTS,
MAX_DEPTH, MAX_UNRESOLVED_SYMBOLS) must independently trigger fallback when
the next planned operation would exceed it.

Tests §18 (partial): fallback disabled via ResolutionConfig.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from engine.repository.materialization.budget import (
    BudgetExceededReason,
    ResolutionBudget,
    ResolutionConfig,
    ResolutionUsage,
)
from engine.repository.materialization.full_index import (
    FallbackResult,
    FullIndexFallback,
)
from engine.repository.resolver.context import ResolutionContext
from engine.repository.resolver.outcome import ResolutionOutcome

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_outcome(reason: BudgetExceededReason, *, files=0, bytes_=0, requests=0, depth=0, symbols=0):
    """Build a budget-exhausted ResolutionOutcome."""
    usage = ResolutionUsage(
        files=files,
        bytes=bytes_,
        remote_requests=requests,
        depth=depth,
        unresolved_symbols=symbols,
    )
    return ResolutionOutcome.budget_exhausted(reason=reason, rounds=depth or 1, usage=usage)


def make_fallback(success: bool = True) -> FullIndexFallback:
    """Return a mock FullIndexFallback that records calls."""
    fb = MagicMock(spec=FullIndexFallback)
    fb.run.return_value = FallbackResult(
        success=success,
        repository_id="github/owner/repo",
        commit_sha="abc123",
        full_repository_files=100,
        full_repository_bytes=1024 * 1024,
    )
    return fb


# ---------------------------------------------------------------------------
# ResolutionOutcome.fallback_required alias
# ---------------------------------------------------------------------------


class TestFallbackRequiredAlias:
    def test_fallback_required_true_when_budget_exceeded(self):
        outcome = make_outcome(BudgetExceededReason.MAX_FILES, files=490)
        assert outcome.budget_exceeded is True
        assert outcome.fallback_required is True

    def test_fallback_required_false_when_complete(self):
        usage = ResolutionUsage(files=10)
        outcome = ResolutionOutcome.success(rounds=1, usage=usage)
        assert outcome.budget_exceeded is False
        assert outcome.fallback_required is False

    def test_metrics_snapshot_includes_fallback_required(self):
        outcome = make_outcome(BudgetExceededReason.MAX_BYTES, bytes_=51 * 1024 * 1024)
        snap = outcome.metrics_snapshot()
        assert "fallback_required" in snap
        assert snap["fallback_required"] is True
        assert snap["budget_exceeded_reason"] == "max_bytes"


# ---------------------------------------------------------------------------
# ResolutionContext budget decisions (pre-check correctness)
# ---------------------------------------------------------------------------


class TestBudgetDecisions:
    """Verify each budget limit fires correctly in ResolutionContext."""

    def test_max_files_exceeded(self):
        budget = ResolutionBudget(max_files=500)
        ctx = ResolutionContext(budget=budget, usage=ResolutionUsage(files=490))
        decision = ctx.can_materialize(files=20, bytes=0, remote_requests=0, depth=1, unresolved_symbols=0)
        assert not decision.allowed
        assert decision.reason == BudgetExceededReason.MAX_FILES

    def test_max_bytes_exceeded(self):
        budget = ResolutionBudget(max_bytes=50 * 1024 * 1024)
        ctx = ResolutionContext(budget=budget, usage=ResolutionUsage(bytes=48 * 1024 * 1024))
        decision = ctx.can_materialize(files=1, bytes=5 * 1024 * 1024, remote_requests=0, depth=1, unresolved_symbols=0)
        assert not decision.allowed
        assert decision.reason == BudgetExceededReason.MAX_BYTES

    def test_max_remote_requests_exceeded(self):
        budget = ResolutionBudget(max_remote_requests=100)
        ctx = ResolutionContext(budget=budget, usage=ResolutionUsage(remote_requests=100))
        decision = ctx.can_materialize(files=1, bytes=0, remote_requests=1, depth=1, unresolved_symbols=0)
        assert not decision.allowed
        assert decision.reason == BudgetExceededReason.MAX_REMOTE_REQUESTS

    def test_max_depth_exceeded(self):
        budget = ResolutionBudget(max_depth=20)
        ctx = ResolutionContext(budget=budget, usage=ResolutionUsage(depth=20))
        decision = ctx.can_materialize(files=0, bytes=0, remote_requests=0, depth=21, unresolved_symbols=0)
        assert not decision.allowed
        assert decision.reason == BudgetExceededReason.MAX_DEPTH

    def test_max_unresolved_symbols_exceeded(self):
        budget = ResolutionBudget(max_unresolved_symbols=1000)
        ctx = ResolutionContext(budget=budget, usage=ResolutionUsage(unresolved_symbols=1000))
        decision = ctx.can_materialize(files=0, bytes=0, remote_requests=0, depth=1, unresolved_symbols=1001)
        assert not decision.allowed
        assert decision.reason == BudgetExceededReason.MAX_UNRESOLVED_SYMBOLS

    def test_within_budget_allowed(self):
        budget = ResolutionBudget(max_files=500)
        ctx = ResolutionContext(budget=budget, usage=ResolutionUsage(files=400))
        decision = ctx.can_materialize(files=50, bytes=0, remote_requests=0, depth=1, unresolved_symbols=0)
        assert decision.allowed
        assert decision.reason is None


# ---------------------------------------------------------------------------
# RepositoryView._should_fallback
# ---------------------------------------------------------------------------


class TestShouldFallback:
    """Unit tests for RepositoryView._should_fallback."""

    def _make_view(self, fallback=None, config=None):
        from engine.repository.overlay.overlay import RepositoryOverlay
        from engine.repository.overlay.view import RepositoryView
        base = MagicMock()
        base.repository_id = "github/owner/repo"
        base.version_id = "github/owner/repo@abc123"
        base._is_indexing_complete = MagicMock(return_value=False)
        overlay = RepositoryOverlay()
        view = RepositoryView(base, overlay, fallback=fallback, config=config)
        return view

    def test_no_fallback_instance_returns_false(self):
        view = self._make_view(fallback=None)
        assert view._should_fallback() is False

    def test_fallback_instance_no_config_returns_true(self):
        view = self._make_view(fallback=make_fallback())
        assert view._should_fallback() is True

    def test_fallback_disabled_via_config(self):
        config = ResolutionConfig(enable_full_index_fallback=False)
        view = self._make_view(fallback=make_fallback(), config=config)
        assert view._should_fallback() is False

    def test_fallback_enabled_via_config(self):
        config = ResolutionConfig(enable_full_index_fallback=True)
        view = self._make_view(fallback=make_fallback(), config=config)
        assert view._should_fallback() is True


# ---------------------------------------------------------------------------
# RepositoryView._is_store_complete
# ---------------------------------------------------------------------------


class TestIsStoreComplete:
    def _make_view(self, complete: bool):
        from engine.repository.overlay.overlay import RepositoryOverlay
        from engine.repository.overlay.view import RepositoryView
        base = MagicMock()
        base.repository_id = "github/owner/repo"
        base.version_id = "github/owner/repo@abc123"
        base._is_indexing_complete = MagicMock(return_value=complete)
        overlay = RepositoryOverlay()
        return RepositoryView(base, overlay)

    def test_complete_store(self):
        view = self._make_view(complete=True)
        assert view._is_store_complete() is True

    def test_incomplete_store(self):
        view = self._make_view(complete=False)
        assert view._is_store_complete() is False

    def test_store_without_method(self):
        from engine.repository.overlay.overlay import RepositoryOverlay
        from engine.repository.overlay.view import RepositoryView
        base = MagicMock(spec=[])  # no methods
        base.repository_id = "github/owner/repo"
        base.version_id = "github/owner/repo@abc123"
        overlay = RepositoryOverlay()
        view = RepositoryView(base, overlay)
        assert view._is_store_complete() is False


# ---------------------------------------------------------------------------
# RepositoryView._trigger_full_index_fallback
# ---------------------------------------------------------------------------


class TestTriggerFullIndexFallback:
    def _make_view(self, fallback):
        from engine.repository.overlay.overlay import RepositoryOverlay
        from engine.repository.overlay.view import RepositoryView
        base = MagicMock()
        base.repository_id = "github/owner/repo"
        base.version_id = "github/owner/repo@abc123"
        base._is_indexing_complete = MagicMock(return_value=False)
        overlay = RepositoryOverlay()
        return RepositoryView(base, overlay, fallback=fallback,
                               repository_id="github/owner/repo",
                               commit_sha="abc123")

    def test_mode_set_to_full_on_success(self):
        fb = make_fallback(success=True)
        view = self._make_view(fb)
        outcome = make_outcome(BudgetExceededReason.MAX_FILES)
        view._trigger_full_index_fallback(outcome)
        assert view._resolution_mode == "FULL"
        assert view._last_fallback_result is not None
        assert view._last_fallback_result.success is True

    def test_mode_remains_lazy_to_full_on_failure(self):
        fb = make_fallback(success=False)
        view = self._make_view(fb)
        outcome = make_outcome(BudgetExceededReason.MAX_BYTES)
        view._trigger_full_index_fallback(outcome)
        assert view._resolution_mode == "LAZY_TO_FULL"

    def test_fallback_run_called_with_correct_args(self):
        fb = make_fallback()
        view = self._make_view(fb)
        ResolutionUsage(files=480)
        outcome = make_outcome(BudgetExceededReason.MAX_FILES, files=480)
        view._trigger_full_index_fallback(outcome)
        fb.run.assert_called_once_with(
            repository_id="github/owner/repo",
            commit_sha="abc123",
            lazy_usage_snapshot=outcome.usage,
            lazy_reason=outcome.reason,
        )


# ---------------------------------------------------------------------------
# Per-threshold fallback trigger tests (§17)
# ---------------------------------------------------------------------------


class TestPerThresholdFallbackTrigger:
    """Each budget limit must independently trigger FullIndexFallback.run()."""

    def _setup(self, reason: BudgetExceededReason, **usage_kwargs):
        """Return (view, mock_fallback) pre-configured for the given reason."""
        from engine.repository.overlay.overlay import RepositoryOverlay
        from engine.repository.overlay.view import RepositoryView
        from engine.repository.store import SQLiteRepositoryStore

        store = SQLiteRepositoryStore(":memory:")
        repo_id = store.create_repository("github", "owner", "repo")
        commit_sha = "abc123"
        version_id = store.create_version(repo_id, commit_sha)
        store.set_version_context(repo_id, version_id)
        store.record_tree(repo_id, commit_sha, [])  # empty tree

        fb = make_fallback(success=True)

        # Wire a resolver that immediately returns budget_exhausted
        mock_resolver = MagicMock()
        usage = ResolutionUsage(**usage_kwargs)
        outcome = ResolutionOutcome.budget_exhausted(reason=reason, rounds=1, usage=usage)
        mock_resolver.resolve_sync.return_value = outcome

        overlay = RepositoryOverlay()
        view = RepositoryView(
            store, overlay,
            resolver=mock_resolver,
            fallback=fb,
            repository_id=repo_id,
            commit_sha=commit_sha,
        )
        return view, fb, store, repo_id, commit_sha

    @patch("core.config.get_compiler_settings")
    def test_max_files_triggers_fallback(self, mock_settings):
        mock_settings.return_value.ENABLE_LAZY_REPOSITORY_RESOLUTION = True
        view, fb, _store, _repo_id, _commit_sha = self._setup(
            BudgetExceededReason.MAX_FILES, files=490
        )
        incomplete_result = MagicMock()
        incomplete_result.complete = False
        from engine.repository.resolver.requirements import FileResolutionRequirement
        req = FileResolutionRequirement("some/file.py")
        view._resolve_if_needed(incomplete_result, req)
        fb.run.assert_called_once()
        assert fb.run.call_args.kwargs["lazy_reason"] == BudgetExceededReason.MAX_FILES

    @patch("core.config.get_compiler_settings")
    def test_max_bytes_triggers_fallback(self, mock_settings):
        mock_settings.return_value.ENABLE_LAZY_REPOSITORY_RESOLUTION = True
        view, fb, *_ = self._setup(
            BudgetExceededReason.MAX_BYTES, bytes=48 * 1024 * 1024
        )
        incomplete_result = MagicMock()
        incomplete_result.complete = False
        from engine.repository.resolver.requirements import FileResolutionRequirement
        req = FileResolutionRequirement("file.py")
        view._resolve_if_needed(incomplete_result, req)
        fb.run.assert_called_once()
        assert fb.run.call_args.kwargs["lazy_reason"] == BudgetExceededReason.MAX_BYTES

    @patch("core.config.get_compiler_settings")
    def test_max_remote_requests_triggers_fallback(self, mock_settings):
        mock_settings.return_value.ENABLE_LAZY_REPOSITORY_RESOLUTION = True
        view, fb, *_ = self._setup(
            BudgetExceededReason.MAX_REMOTE_REQUESTS, remote_requests=100
        )
        incomplete_result = MagicMock()
        incomplete_result.complete = False
        from engine.repository.resolver.requirements import FileResolutionRequirement
        req = FileResolutionRequirement("x.py")
        view._resolve_if_needed(incomplete_result, req)
        fb.run.assert_called_once()
        assert fb.run.call_args.kwargs["lazy_reason"] == BudgetExceededReason.MAX_REMOTE_REQUESTS

    @patch("core.config.get_compiler_settings")
    def test_max_depth_triggers_fallback(self, mock_settings):
        mock_settings.return_value.ENABLE_LAZY_REPOSITORY_RESOLUTION = True
        view, fb, *_ = self._setup(
            BudgetExceededReason.MAX_DEPTH, depth=20
        )
        incomplete_result = MagicMock()
        incomplete_result.complete = False
        from engine.repository.resolver.requirements import FileResolutionRequirement
        req = FileResolutionRequirement("d.py")
        view._resolve_if_needed(incomplete_result, req)
        fb.run.assert_called_once()
        assert fb.run.call_args.kwargs["lazy_reason"] == BudgetExceededReason.MAX_DEPTH

    @patch("core.config.get_compiler_settings")
    def test_max_unresolved_symbols_triggers_fallback(self, mock_settings):
        mock_settings.return_value.ENABLE_LAZY_REPOSITORY_RESOLUTION = True
        view, fb, *_ = self._setup(
            BudgetExceededReason.MAX_UNRESOLVED_SYMBOLS, unresolved_symbols=1000
        )
        incomplete_result = MagicMock()
        incomplete_result.complete = False
        from engine.repository.resolver.requirements import FileResolutionRequirement
        req = FileResolutionRequirement("s.py")
        view._resolve_if_needed(incomplete_result, req)
        fb.run.assert_called_once()
        assert fb.run.call_args.kwargs["lazy_reason"] == BudgetExceededReason.MAX_UNRESOLVED_SYMBOLS

    @patch("core.config.get_compiler_settings")
    def test_fallback_not_triggered_when_within_budget(self, mock_settings):
        """Successful lazy resolution must NOT invoke the fallback."""
        from engine.repository.overlay.overlay import RepositoryOverlay
        from engine.repository.overlay.view import RepositoryView
        from engine.repository.store import SQLiteRepositoryStore

        mock_settings.return_value.ENABLE_LAZY_REPOSITORY_RESOLUTION = True
        store = SQLiteRepositoryStore(":memory:")
        repo_id = store.create_repository("github", "owner", "repo")
        commit_sha = "abc123"
        version_id = store.create_version(repo_id, commit_sha)
        store.set_version_context(repo_id, version_id)
        store.record_tree(repo_id, commit_sha, [])

        fb = make_fallback()

        mock_resolver = MagicMock()
        usage = ResolutionUsage(files=10)
        outcome = ResolutionOutcome.success(rounds=1, usage=usage)
        mock_resolver.resolve_sync.return_value = outcome

        overlay = RepositoryOverlay()
        view = RepositoryView(
            store, overlay,
            resolver=mock_resolver,
            fallback=fb,
            repository_id=repo_id,
            commit_sha=commit_sha,
        )
        incomplete_result = MagicMock()
        incomplete_result.complete = False
        from engine.repository.resolver.requirements import FileResolutionRequirement
        req = FileResolutionRequirement("fine.py")
        view._resolve_if_needed(incomplete_result, req)
        fb.run.assert_not_called()

    @patch("core.config.get_compiler_settings")
    def test_fallback_disabled_by_config(self, mock_settings):
        """When enable_full_index_fallback=False, budget exceeded must NOT invoke fallback."""
        from engine.repository.overlay.overlay import RepositoryOverlay
        from engine.repository.overlay.view import RepositoryView
        from engine.repository.store import SQLiteRepositoryStore

        mock_settings.return_value.ENABLE_LAZY_REPOSITORY_RESOLUTION = True
        store = SQLiteRepositoryStore(":memory:")
        repo_id = store.create_repository("github", "owner", "repo")
        commit_sha = "def456"
        version_id = store.create_version(repo_id, commit_sha)
        store.set_version_context(repo_id, version_id)
        store.record_tree(repo_id, commit_sha, [])

        fb = make_fallback()
        config = ResolutionConfig(enable_full_index_fallback=False)

        mock_resolver = MagicMock()
        usage = ResolutionUsage(files=490)
        outcome = ResolutionOutcome.budget_exhausted(
            reason=BudgetExceededReason.MAX_FILES, rounds=1, usage=usage
        )
        mock_resolver.resolve_sync.return_value = outcome

        overlay = RepositoryOverlay()
        view = RepositoryView(
            store, overlay,
            resolver=mock_resolver,
            fallback=fb,
            config=config,
            repository_id=repo_id,
            commit_sha=commit_sha,
        )
        incomplete_result = MagicMock()
        incomplete_result.complete = False
        from engine.repository.resolver.requirements import FileResolutionRequirement
        req = FileResolutionRequirement("blocked.py")
        view._resolve_if_needed(incomplete_result, req)
        fb.run.assert_not_called()

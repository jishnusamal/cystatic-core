"""Phase 12 — Regression tests (§19, §20, §21).

§19 — Compiler opacity: fallback symbols must not appear in any compiler module.
§20 — No infinite fallback loop: after full indexing, resolver is not re-entered.
§21 — Per-request isolation: fallback state does not leak between requests.
"""

from __future__ import annotations

import ast
import importlib
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from engine.repository.materialization.budget import BudgetExceededReason, ResolutionUsage
from engine.repository.materialization.full_index import FallbackResult, FullIndexFallback
from engine.repository.resolver.outcome import ResolutionOutcome


# ---------------------------------------------------------------------------
# §19 — Compiler opacity
# ---------------------------------------------------------------------------

_COMPILER_MODULES = [
    "engine.change",
    "engine.behavior",
    "engine.operational",
    "engine.discovery",
    "engine.review_context",
    "engine.llm_context",
]

_FORBIDDEN_SYMBOLS = [
    "FullIndexFallback",
    "FallbackResult",
    "ResolutionConfig",
    "fallback_triggered",
    "fallback_reason",
    "FullIndexFallback",
    "ResolutionBudget",
    "ResolutionUsage",
    "RepositoryMaterializer",
    "RepositoryResolver",
]


def _python_files_under(package: str) -> list[Path]:
    """Return all .py files under a Python package directory."""
    base = Path("engine") / package.split(".")[-1]
    if not base.exists():
        # Try multi-segment path
        base = Path(*package.split("."))
    if not base.exists():
        return []
    return list(base.rglob("*.py"))


def _file_contains_any(path: Path, symbols: list[str]) -> list[str]:
    """Return which forbidden symbols appear as names in a file."""
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except Exception:
        return []

    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in symbols:
            found.append(node.id)
        elif isinstance(node, ast.Attribute) and node.attr in symbols:
            found.append(node.attr)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if any(s in alias.name for s in symbols):
                    found.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.names:
                for alias in node.names:
                    if alias.name in symbols:
                        found.append(alias.name)
    return list(set(found))


class TestCompilerOpacity:
    """Verify that fallback types never appear in compiler modules."""

    @pytest.mark.parametrize("package", _COMPILER_MODULES)
    def test_compiler_package_is_fallback_free(self, package):
        pkg_path = Path(*package.split("."))
        if not pkg_path.exists():
            pytest.skip(f"Package directory not found: {pkg_path}")

        violations: list[str] = []
        for py_file in pkg_path.rglob("*.py"):
            found = _file_contains_any(py_file, _FORBIDDEN_SYMBOLS)
            for sym in found:
                violations.append(f"{py_file}: {sym}")

        assert not violations, (
            "Compiler modules must not reference fallback/resolver internals:\n"
            + "\n".join(violations)
        )


# ---------------------------------------------------------------------------
# §20 — No infinite fallback loop
# ---------------------------------------------------------------------------


class TestNoInfiniteFallbackLoop:
    """After successful full indexing, _resolve_if_needed must not re-enter resolver."""

    def _make_view_with_complete_store(self):
        from engine.repository.overlay.view import RepositoryView
        from engine.repository.overlay.overlay import RepositoryOverlay
        from engine.repository.store import SQLiteRepositoryStore

        store = SQLiteRepositoryStore(":memory:")
        repo_id = store.create_repository("github", "owner", "repo")
        commit_sha = "abc123"
        version_id = store.create_version(repo_id, commit_sha)
        store.set_version_context(repo_id, version_id)
        store.record_tree(repo_id, commit_sha, [])
        # Mark as complete — simulates post-fallback state
        store.set_indexed_complete(repo_id, commit_sha, True)

        mock_resolver = MagicMock()
        mock_fallback = MagicMock(spec=FullIndexFallback)

        overlay = RepositoryOverlay()
        view = RepositoryView(
            store, overlay,
            resolver=mock_resolver,
            fallback=mock_fallback,
            repository_id=repo_id,
            commit_sha=commit_sha,
        )
        return view, mock_resolver, mock_fallback

    @patch("core.config.get_compiler_settings")
    def test_resolver_not_called_when_store_complete(self, mock_settings):
        mock_settings.return_value.ENABLE_LAZY_REPOSITORY_RESOLUTION = True
        view, mock_resolver, mock_fallback = self._make_view_with_complete_store()

        incomplete_result = MagicMock()
        incomplete_result.complete = False

        from engine.repository.resolver.requirements import FileResolutionRequirement
        for i in range(3):
            req = FileResolutionRequirement(f"file_{i}.py")
            result = view._resolve_if_needed(incomplete_result, req)
            assert result is False, f"Expected False on attempt {i}"

        mock_resolver.resolve_sync.assert_not_called()
        mock_fallback.run.assert_not_called()

    @patch("core.config.get_compiler_settings")
    def test_fallback_not_called_when_store_complete(self, mock_settings):
        mock_settings.return_value.ENABLE_LAZY_REPOSITORY_RESOLUTION = True
        view, _, mock_fallback = self._make_view_with_complete_store()

        incomplete_result = MagicMock()
        incomplete_result.complete = False
        from engine.repository.resolver.requirements import FileResolutionRequirement
        view._resolve_if_needed(incomplete_result, FileResolutionRequirement("x.py"))
        mock_fallback.run.assert_not_called()


# ---------------------------------------------------------------------------
# §21 — Per-request isolation
# ---------------------------------------------------------------------------


class TestFallbackStateIsolation:
    """Fallback state (indexed_complete) belongs to (repo_id, commit_sha), not global."""

    @patch("core.config.get_compiler_settings")
    def test_two_different_repos_are_independent(self, mock_settings):
        mock_settings.return_value.ENABLE_LAZY_REPOSITORY_RESOLUTION = True
        from engine.repository.overlay.view import RepositoryView
        from engine.repository.overlay.overlay import RepositoryOverlay
        from engine.repository.store import SQLiteRepositoryStore

        # Request A — triggers fallback → store A becomes complete
        store_a = SQLiteRepositoryStore(":memory:")
        repo_id_a = store_a.create_repository("github", "owner", "repo_a")
        commit_a = "sha_a"
        vid_a = store_a.create_version(repo_id_a, commit_a)
        store_a.set_version_context(repo_id_a, vid_a)
        store_a.record_tree(repo_id_a, commit_a, [])
        store_a.set_indexed_complete(repo_id_a, commit_a, True)  # post-fallback

        # Request B — different repo, should NOT inherit complete state
        store_b = SQLiteRepositoryStore(":memory:")
        repo_id_b = store_b.create_repository("github", "owner", "repo_b")
        commit_b = "sha_b"
        vid_b = store_b.create_version(repo_id_b, commit_b)
        store_b.set_version_context(repo_id_b, vid_b)
        store_b.record_tree(repo_id_b, commit_b, [])
        # Do NOT set indexed_complete for store_b

        mock_resolver_b = MagicMock()
        usage_b = ResolutionUsage(files=10)
        outcome_b = ResolutionOutcome.success(rounds=1, usage=usage_b)
        mock_resolver_b.resolve_sync.return_value = outcome_b

        overlay = RepositoryOverlay()
        view_b = RepositoryView(
            store_b, overlay,
            resolver=mock_resolver_b,
            repository_id=repo_id_b,
            commit_sha=commit_b,
        )

        # store_a being complete must not affect store_b
        assert view_b._is_store_complete() is False

        incomplete_result = MagicMock()
        incomplete_result.complete = False
        from engine.repository.resolver.requirements import FileResolutionRequirement
        req_b = FileResolutionRequirement("some.py")
        view_b._resolve_if_needed(incomplete_result, req_b)

        # Resolver B should have been called (store B is not complete)
        mock_resolver_b.resolve_sync.assert_called_once()

    def test_per_request_isolation_complete_flag(self):
        """set_indexed_complete on repo/commit A must not affect repo/commit B."""
        from engine.repository.store import SQLiteRepositoryStore

        store = SQLiteRepositoryStore(":memory:")
        repo_id_a = store.create_repository("github", "owner", "repo")
        commit_a = "commit_a"
        commit_b = "commit_b"
        vid_a = store.create_version(repo_id_a, commit_a)
        vid_b = store.create_version(repo_id_a, commit_b)

        store.set_version_context(repo_id_a, vid_a)
        store.record_tree(repo_id_a, commit_a, [])
        store.set_indexed_complete(repo_id_a, commit_a, True)

        store.set_version_context(repo_id_a, vid_b)
        store.record_tree(repo_id_a, commit_b, [])

        # Commit B must not be marked complete
        assert store._is_indexing_complete() is False

"""Phase 12 — Full-index fallback.

When lazy resolution exceeds its budget, the repository layer can invoke
:class:`FullIndexFallback` to acquire and index the complete repository,
ensuring analysis always completes.

Key invariant
-------------
*Lazy resolution is an optimisation, not a correctness requirement.*

The fallback reuses the existing :class:`RepositoryIndexer` and
:class:`RepositoryStore` — it does **not** introduce a second indexing
pipeline.  After the fallback, ``store.set_indexed_complete(True)`` marks
the commit as fully indexed so subsequent queries need not re-enter the
resolver.

Ownership
---------
::

    RepositoryView
          │ budget exceeded (ResolutionOutcome.budget_exceeded=True)
          ▼
    FullIndexFallback
          │ get_files(all paths, commit_sha)
          ▼
    RepositoryProvider
          │
          ▼
    RepositoryIndexer.index_files(...)
          │
          ▼
    RepositoryStore
          │ set_indexed_complete(True)
          ▼
    RepositoryView queries → direct store answers
"""

from __future__ import annotations

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

from core.logging import pipeline_logger
from engine.repository.indexing.indexer import RepositoryIndexer
from engine.repository.materialization.budget import BudgetExceededReason
from engine.repository.store import RepositoryStore
from integrations.base import RepositoryProvider


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FallbackResult:
    """Immutable result returned by :meth:`FullIndexFallback.run`.

    All timing fields are in seconds.
    """

    success: bool
    repository_id: str
    commit_sha: str

    # Coverage after full indexing
    full_repository_files: int = 0
    full_repository_bytes: int = 0

    # Timing
    full_acquisition_duration_s: float = 0.0
    full_indexing_duration_s: float = 0.0
    fallback_duration_s: float = 0.0

    # Context captured at the fallback decision point
    lazy_files_before: int = 0
    lazy_bytes_before: int = 0
    lazy_remote_requests_before: int = 0
    lazy_depth_before: int = 0
    lazy_unresolved_symbols_before: int = 0
    fallback_reason: str | None = None

    # Error string (None on success)
    error: str | None = None

    def metrics_snapshot(self) -> dict:
        """Return a machine-readable summary suitable for structured logging."""
        return {
            "success": self.success,
            "full_repository_files": self.full_repository_files,
            "full_repository_bytes": self.full_repository_bytes,
            "full_acquisition_duration_s": round(self.full_acquisition_duration_s, 3),
            "full_indexing_duration_s": round(self.full_indexing_duration_s, 3),
            "fallback_duration_s": round(self.fallback_duration_s, 3),
            "lazy_files_before": self.lazy_files_before,
            "lazy_bytes_before": self.lazy_bytes_before,
            "lazy_remote_requests_before": self.lazy_remote_requests_before,
            "lazy_depth_before": self.lazy_depth_before,
            "lazy_unresolved_symbols_before": self.lazy_unresolved_symbols_before,
            "fallback_reason": self.fallback_reason,
            "error": self.error,
        }


# ---------------------------------------------------------------------------
# Fallback component
# ---------------------------------------------------------------------------


class FullIndexFallback:
    """Transition from lazy resolution to full-repository indexing.

    Parameters
    ----------
    source:
        The provider used to fetch repository blobs.  The same instance
        used by the lazy materializer is appropriate.
    store:
        The repository fact store.  Must be the same store that lazy
        resolution has been writing into.
    indexer:
        The shared :class:`RepositoryIndexer` instance.  Re-using the
        same instance preserves the in-memory file/symbol ID maps,
        which prevents duplicate allocations when the indexer encounters
        files that were already lazily indexed.
    batch_size:
        Number of blobs to fetch per provider call.  Defaults to 100
        (matching the materializer's default).

    Notes
    -----
    * The fallback calls ``store.set_indexed_complete(True)`` after a
      successful full index so that :meth:`RepositoryView._resolve_if_needed`
      bypasses the resolver on subsequent queries.
    * Files that are already materialised (``indexed_status='indexed'``) are
      **skipped during acquisition** to avoid unnecessary network calls.
      Their facts already exist in the store; the indexer ID maps
      include them via :meth:`RepositoryIndexer._sync_mappings_from_sink`.
    * The public interface (:meth:`run`) is **synchronous** to match
      ``resolver.resolve_sync()``, which
      :meth:`RepositoryView._resolve_if_needed` already calls synchronously.
      Internal async work runs in a dedicated thread via :func:`asyncio.run`.
    """

    def __init__(
        self,
        source: RepositoryProvider,
        store: RepositoryStore,
        indexer: RepositoryIndexer,
        batch_size: int = 100,
    ) -> None:
        self.source = source
        self.store = store
        self.indexer = indexer
        self.batch_size = batch_size

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def run(
        self,
        repository_id: str,
        commit_sha: str,
        *,
        lazy_usage_snapshot: Any | None = None,
        lazy_reason: BudgetExceededReason | None = None,
    ) -> FallbackResult:
        """Execute the full-index fallback synchronously.

        Parameters
        ----------
        repository_id:
            Repository identifier, e.g. ``"github/acme/backend"``.
        commit_sha:
            The **exact base commit** that lazy resolution was targeting.
            The fallback must index the same commit to prevent cross-commit
            fact contamination.
        lazy_usage_snapshot:
            Optional :class:`ResolutionUsage` captured at the point the
            budget was exhausted.  Used for metrics only.
        lazy_reason:
            The :class:`BudgetExceededReason` that triggered the fallback.
        """
        coro = self._run_async(
            repository_id=repository_id,
            commit_sha=commit_sha,
            lazy_usage_snapshot=lazy_usage_snapshot,
            lazy_reason=lazy_reason,
        )

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(asyncio.run, coro)
                return future.result()
        else:
            return asyncio.run(coro)

    # ------------------------------------------------------------------
    # Internal async implementation
    # ------------------------------------------------------------------

    async def _run_async(
        self,
        repository_id: str,
        commit_sha: str,
        *,
        lazy_usage_snapshot: Any | None = None,
        lazy_reason: BudgetExceededReason | None = None,
    ) -> FallbackResult:
        fallback_start = time.perf_counter()

        # Capture lazy usage for metrics
        lazy_files = getattr(lazy_usage_snapshot, "files", 0) if lazy_usage_snapshot else 0
        lazy_bytes = getattr(lazy_usage_snapshot, "bytes", 0) if lazy_usage_snapshot else 0
        lazy_remote_requests = getattr(lazy_usage_snapshot, "remote_requests", 0) if lazy_usage_snapshot else 0
        lazy_depth = getattr(lazy_usage_snapshot, "depth", 0) if lazy_usage_snapshot else 0
        lazy_symbols = getattr(lazy_usage_snapshot, "unresolved_symbols", 0) if lazy_usage_snapshot else 0
        reason_str = lazy_reason.value if lazy_reason is not None else None

        self._log(
            "full_index_fallback_started",
            repository=repository_id,
            commit=commit_sha,
            lazy_files=lazy_files,
            lazy_bytes=lazy_bytes,
            lazy_remote_requests=lazy_remote_requests,
            lazy_depth=lazy_depth,
            lazy_unresolved_symbols=lazy_symbols,
            fallback_reason=reason_str,
        )

        try:
            # ------------------------------------------------------------------
            # 1. Discover all blob paths in the recorded tree for this commit
            # ------------------------------------------------------------------
            all_tree_paths = self._get_all_tree_paths(repository_id, commit_sha)
            if not all_tree_paths:
                return FallbackResult(
                    success=False,
                    repository_id=repository_id,
                    commit_sha=commit_sha,
                    error="no tree entries found; tree may not have been recorded",
                    fallback_duration_s=time.perf_counter() - fallback_start,
                    fallback_reason=reason_str,
                    lazy_files_before=lazy_files,
                    lazy_bytes_before=lazy_bytes,
                    lazy_remote_requests_before=lazy_remote_requests,
                    lazy_depth_before=lazy_depth,
                    lazy_unresolved_symbols_before=lazy_symbols,
                )

            # ------------------------------------------------------------------
            # 2. Determine which paths still need materialisation
            # ------------------------------------------------------------------
            already_done = set(
                self.store.get_materialized_paths(repository_id, commit_sha)
            )
            remaining_paths = [p for p in all_tree_paths if p not in already_done]

            self._log(
                "full_index_fallback_paths",
                repository=repository_id,
                commit=commit_sha,
                total_paths=len(all_tree_paths),
                already_materialized=len(already_done),
                to_fetch=len(remaining_paths),
            )

            # ------------------------------------------------------------------
            # 3. Sync indexer ID maps from existing store facts
            #    (prevents file/symbol ID collisions for already-lazy-indexed files)
            # ------------------------------------------------------------------
            self.indexer._sync_mappings_from_sink()

            # ------------------------------------------------------------------
            # 4. Fetch remaining blobs in batches and index each
            # ------------------------------------------------------------------
            acq_total_s = 0.0
            idx_total_s = 0.0
            total_bytes = 0

            batches = [
                remaining_paths[i : i + self.batch_size]
                for i in range(0, len(remaining_paths), self.batch_size)
            ]

            for batch_idx, batch in enumerate(batches):
                # Acquisition
                acq_start = time.perf_counter()
                blobs = await self.source.get_files(repository_id, batch, commit_sha)
                acq_total_s += time.perf_counter() - acq_start

                # Index
                idx_start = time.perf_counter()
                files_to_index: dict[str, str] = {}
                for blob in blobs:
                    try:
                        content_str = blob.content.decode("utf-8")
                        files_to_index[blob.path] = content_str
                        total_bytes += len(blob.content)
                    except (UnicodeDecodeError, UnicodeError):
                        # Binary file — record as materialised with empty content
                        self.store.record_materialization(
                            repository_id, commit_sha, blob.path,
                            blob.sha, "indexed",
                        )

                if files_to_index:
                    self.indexer.index_files(files_to_index)

                idx_total_s += time.perf_counter() - idx_start

                self._log(
                    "full_index_fallback_batch",
                    repository=repository_id,
                    commit=commit_sha,
                    batch_index=batch_idx,
                    batch_size=len(batch),
                    fetched=len(blobs),
                    indexed=len(files_to_index),
                )

            # ------------------------------------------------------------------
            # 5. Transition RepositoryStore coverage to COMPLETE
            # ------------------------------------------------------------------
            self.store.set_indexed_complete(repository_id, commit_sha, True)

            fallback_duration_s = time.perf_counter() - fallback_start

            self._log(
                "full_index_fallback_complete",
                repository=repository_id,
                commit=commit_sha,
                full_repository_files=len(all_tree_paths),
                full_repository_bytes=total_bytes,
                full_acquisition_duration_s=round(acq_total_s, 3),
                full_indexing_duration_s=round(idx_total_s, 3),
                fallback_duration_s=round(fallback_duration_s, 3),
            )

            return FallbackResult(
                success=True,
                repository_id=repository_id,
                commit_sha=commit_sha,
                full_repository_files=len(all_tree_paths),
                full_repository_bytes=total_bytes,
                full_acquisition_duration_s=acq_total_s,
                full_indexing_duration_s=idx_total_s,
                fallback_duration_s=fallback_duration_s,
                lazy_files_before=lazy_files,
                lazy_bytes_before=lazy_bytes,
                lazy_remote_requests_before=lazy_remote_requests,
                lazy_depth_before=lazy_depth,
                lazy_unresolved_symbols_before=lazy_symbols,
                fallback_reason=reason_str,
            )

        except Exception as exc:
            fallback_duration_s = time.perf_counter() - fallback_start
            error_msg = str(exc)
            self._log(
                "full_index_fallback_failed",
                repository=repository_id,
                commit=commit_sha,
                error=error_msg,
                fallback_duration_s=round(fallback_duration_s, 3),
            )
            return FallbackResult(
                success=False,
                repository_id=repository_id,
                commit_sha=commit_sha,
                fallback_duration_s=fallback_duration_s,
                lazy_files_before=lazy_files,
                lazy_bytes_before=lazy_bytes,
                lazy_remote_requests_before=lazy_remote_requests,
                lazy_depth_before=lazy_depth,
                lazy_unresolved_symbols_before=lazy_symbols,
                fallback_reason=reason_str,
                error=error_msg,
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_all_tree_paths(
        self, repository_id: str, commit_sha: str
    ) -> list[str]:
        """Return all blob paths recorded in the repository tree for this commit."""
        if not hasattr(self.store, "conn"):
            return []
        try:
            cur = self.store.conn.cursor()
            cur.execute(
                "SELECT path FROM repository_tree "
                "WHERE repository_id = ? AND commit_sha = ? AND type = 'blob'",
                (repository_id, commit_sha),
            )
            return [row[0] for row in cur.fetchall()]
        except Exception:
            return []

    def _log(self, event: str, **kwargs: Any) -> None:
        """Emit a structured event to the logging system."""
        import json

        ctx = pipeline_logger.current_context
        if ctx and hasattr(ctx, "log_manager") and ctx.log_manager:
            ctx.log_manager.log_structured_event(
                phase="repository",
                event=event,
                to_terminal=True,
                **kwargs,
            )
        else:
            payload = {"phase": "repository", "event": event, **kwargs}
            pipeline_logger.log_pipeline(json.dumps(payload), to_terminal=True)

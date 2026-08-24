from __future__ import annotations

import asyncio
import math
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from core.logging import pipeline_logger
from engine.repository.materialization.budget import (
    ResolutionBudget,
    ResolutionUsage,
)
from engine.repository.materialization.materializer import RepositoryMaterializer
from engine.repository.materialization.request import MaterializationRequest
from engine.repository.store import RepositoryStore
from integrations.base import RepositoryProvider

from .context import ResolutionContext
from .frontier import ResolutionFrontier
from .outcome import ResolutionOutcome
from .planner import DefaultRequirementPlanner, RequirementPlanner
from .requirements import ResolutionRequirement, SymbolResolutionRequirement


class RepositoryResolver:
    """Coordinates lazy-resolution: plans requirements, creates materialization
    requests, invokes the materializer, and updates the repository store.

    The resolver enforces a :class:`ResolutionBudget` on behalf of the
    analysis request.  Budget checks happen **before** any provider
    acquisition so that no batch can silently exceed the configured limits.

    Ownership::

        RepositoryView
               │
               ▼
        RepositoryResolver   ← enforces ResolutionBudget
               │
               ▼
        RepositoryMaterializer
    """

    def __init__(
        self,
        store: RepositoryStore,
        source: RepositoryProvider,
        materializer: RepositoryMaterializer,
        planner: RequirementPlanner | None = None,
        tree_metadata: Any = None,
        base_commit: str | None = None,
        budget: ResolutionBudget | Any | None = None,
    ) -> None:
        self.store = store
        self.source = source
        self.materializer = materializer
        self.planner = planner or DefaultRequirementPlanner(store, source)
        if hasattr(self.planner, "set_indexer") and self.materializer:
            self.planner.set_indexer(self.materializer.indexer)
        self.tree_metadata = tree_metadata
        self.base_commit = base_commit

        # Accept either a ResolutionBudget or the legacy MaterializationBudget
        # (they are now the same type via alias).  Fall back to defaults.
        if isinstance(budget, ResolutionBudget):
            self._budget = budget
        elif budget is not None:
            # Coerce from an object that may have max_files / max_bytes attrs
            self._budget = ResolutionBudget(
                max_files=getattr(budget, "max_files", 500),
                max_bytes=getattr(budget, "max_bytes", 50 * 1024 * 1024),
                max_remote_requests=getattr(budget, "max_remote_requests", 100),
                max_depth=getattr(budget, "max_depth", 20),
                max_unresolved_symbols=getattr(budget, "max_unresolved_symbols", 1_000),
            )
        else:
            self._budget = ResolutionBudget()

        # For backward-compat, expose as self.budget (read-only alias)
        self.budget = self._budget

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _make_context(
        self,
        repository_id: str | None = None,
        commit_sha: str | None = None,
        request_id: str | None = None,
    ) -> ResolutionContext:
        """Create a fresh, request-scoped ResolutionContext."""
        return ResolutionContext(
            budget=self._budget,
            usage=ResolutionUsage(),
            request_id=request_id,
            repository_id=repository_id,
            commit_sha=commit_sha,
        )

    def _estimate_batch(
        self,
        to_materialize: list[tuple[str, Any, int]],
        batch_size: int,
    ) -> tuple[int, int, int]:
        """Return (num_files, num_bytes, num_remote_requests) for a planned batch."""
        num_files = len(to_materialize)
        num_bytes = sum(size for _, _, size in to_materialize)
        num_remote = math.ceil(num_files / batch_size) if num_files > 0 else 0
        return num_files, num_bytes, num_remote

    def _emit(self, event: str, **kwargs: Any) -> None:
        """Emit a structured event to the logging system."""
        import json
        ctx = pipeline_logger.current_context
        if ctx and hasattr(ctx, "log_manager") and ctx.log_manager:
            ctx.log_manager.log_structured_event(
                phase="resolver",
                event=event,
                to_terminal=True,
                **kwargs,
            )
        else:
            payload = {"phase": "resolver", "event": event, **kwargs}
            pipeline_logger.log_pipeline(json.dumps(payload), to_terminal=True)

    # ------------------------------------------------------------------
    # Core resolution loop
    # ------------------------------------------------------------------

    async def resolve(
        self,
        repository_id: str,
        commit_sha: str,
        requirements: Sequence[ResolutionRequirement],
        *,
        context: ResolutionContext | None = None,
    ) -> ResolutionOutcome:
        """Asynchronously resolve a set of requirements.

        For each frontier iteration the resolver:

        1. Collects unresolved requirements.
        2. Checks the unresolved-symbol budget.
        3. Plans candidate paths via the planner.
        4. Calculates estimated files / bytes / remote-requests.
        5. Checks file / byte / request budget.
        6. Checks traversal depth.
        7. Materializes the batch.
        8. Updates usage from actual ``MaterializationResult``.
        9. Expands the frontier.

        Returns a :class:`ResolutionOutcome` — the caller (``RepositoryView``)
        may inspect ``budget_exceeded`` for observability.  Downstream
        compilers never see this object.
        """
        # Each call gets its own context unless one was supplied (testing).
        ctx = context or self._make_context(
            repository_id=repository_id,
            commit_sha=commit_sha,
        )

        # Build initial frontier
        frontier = ResolutionFrontier()
        for req in requirements:
            frontier.unresolved.add(req)
            if isinstance(req, SymbolResolutionRequirement):
                frontier.add_symbol(req.symbol_id)

        pipeline_logger.log_pipeline(
            f"[Resolver] Starting frontier resolution with {len(requirements)} requirements "
            f"for {repository_id}@{commit_sha}",
            to_terminal=True,
        )

        round_num = 0

        while frontier.has_work():
            round_num += 1
            ctx.usage.depth = round_num  # depth == frontier iteration

            # ----------------------------------------------------------------
            # 1. Collect current requirements
            # ----------------------------------------------------------------
            current_reqs = list(frontier.unresolved)
            pipeline_logger.log_pipeline(
                f"[Resolver][Round {round_num}] Planning {len(current_reqs)} requirements",
                to_terminal=True,
            )

            # ----------------------------------------------------------------
            # 2. Check unresolved-symbol budget (before planning)
            # ----------------------------------------------------------------
            symbol_ids = {
                req.symbol_id
                for req in current_reqs
                if isinstance(req, SymbolResolutionRequirement)
            }
            ctx.usage.record_symbols(symbol_ids)

            sym_decision = ctx.can_materialize(
                files=0,
                bytes=0,
                remote_requests=0,
                depth=round_num,
                unresolved_symbols=ctx.usage.unresolved_symbols,
            )
            if not sym_decision.allowed:
                pipeline_logger.log_pipeline(
                    f"[Resolver][Round {round_num}] Budget exceeded: {sym_decision.reason}",
                    to_terminal=True,
                )
                self._emit(
                    "resolver_budget_exceeded",
                    repository=repository_id,
                    commit=commit_sha,
                    round=round_num,
                    reason=sym_decision.reason.value if sym_decision.reason else None,
                    **ctx.metrics_snapshot(),
                )
                return ResolutionOutcome.budget_exhausted(
                    reason=sym_decision.reason,  # type: ignore[arg-type]
                    rounds=round_num,
                    usage=ctx.usage,
                )

            # ----------------------------------------------------------------
            # 3. Plan candidate paths
            # ----------------------------------------------------------------
            candidate_requests = await self.planner.plan(
                repository_id, commit_sha, current_reqs
            )

            # ----------------------------------------------------------------
            # 4. Aggregate paths that need materialization (pre-deduplicated)
            # ----------------------------------------------------------------
            missing_paths: set[str] = set()
            size_by_path: dict[str, int] = {}

            for req in candidate_requests:
                for p in req.paths:
                    if not self.store.is_materialized(repository_id, commit_sha, p):
                        missing_paths.add(p)

            pipeline_logger.log_pipeline(
                f"[Resolver][Round {round_num}] {len(candidate_requests)} candidate requests, "
                f"{len(missing_paths)} missing paths",
                to_terminal=True,
            )

            if missing_paths:
                # ----------------------------------------------------------------
                # 5. Estimate bytes from tree metadata (pre-acquisition)
                # ----------------------------------------------------------------
                tree_entries = self.store.get_tree_entries(
                    repository_id, commit_sha, list(missing_paths)
                )
                for path in missing_paths:
                    entry = tree_entries.get(path) or {}
                    size_by_path[path] = entry.get("size", 0)

                batch_size = getattr(self.materializer, "materialization_batch_size", 100)
                to_materialize_list = [
                    (p, size_by_path.get(p, 0)) for p in sorted(missing_paths)
                ]
                num_files = len(to_materialize_list)
                num_bytes = sum(sz for _, sz in to_materialize_list)
                num_remote = math.ceil(num_files / batch_size) if num_files > 0 else 0

                # ----------------------------------------------------------------
                # 6. Pre-materialization budget check (files, bytes, requests, depth)
                # ----------------------------------------------------------------
                decision = ctx.can_materialize(
                    files=num_files,
                    bytes=num_bytes,
                    remote_requests=num_remote,
                    depth=round_num,
                    unresolved_symbols=ctx.usage.unresolved_symbols,
                )

                if not decision.allowed:
                    pipeline_logger.log_pipeline(
                        f"[Resolver][Round {round_num}] Pre-materialization budget exceeded: "
                        f"{decision.reason} "
                        f"(planned {num_files} files, {num_bytes} bytes, {num_remote} requests)",
                        to_terminal=True,
                    )
                    self._emit(
                        "resolver_budget_exceeded",
                        repository=repository_id,
                        commit=commit_sha,
                        round=round_num,
                        reason=decision.reason.value if decision.reason else None,
                        planned_files=num_files,
                        planned_bytes=num_bytes,
                        planned_remote_requests=num_remote,
                        **ctx.metrics_snapshot(),
                    )
                    return ResolutionOutcome.budget_exhausted(
                        reason=decision.reason,  # type: ignore[arg-type]
                        rounds=round_num,
                        usage=ctx.usage,
                    )

                # ----------------------------------------------------------------
                # 7. Materialize batch (budget already checked)
                # ----------------------------------------------------------------
                request = MaterializationRequest(
                    repository_id=repository_id,
                    commit_sha=commit_sha,
                    paths=tuple(sorted(missing_paths)),
                    reason="resolution_frontier",
                )
                result = await self.materializer.materialize(request)

                # ----------------------------------------------------------------
                # 8. Update usage from ACTUAL materialization result
                #
                # Planned vs actual may differ (e.g. some paths failed or were
                # already materialized mid-batch).  Usage reflects what was
                # successfully acquired.
                # ----------------------------------------------------------------
                actual_paths = list(result.materialized_paths)
                actual_bytes_by_path: dict[str, int] = {}
                for p in actual_paths:
                    # Use tree entry size as best proxy for actual bytes per file
                    actual_bytes_by_path[p] = size_by_path.get(p, 0)

                ctx.usage.record_paths(actual_paths, actual_bytes_by_path)
                # remote_requests: each materializer.materialize() call is
                # internally batched; count batches that ran (approximated as 1
                # top-level call here; the materializer tracks fine-grained
                # remote_requests in its own metrics).
                ctx.usage.remote_requests += result.bytes_fetched > 0 and 1 or 0

                pipeline_logger.log_pipeline(
                    f"[Resolver][Round {round_num}] Materialized {len(actual_paths)} files "
                    f"({result.bytes_fetched} bytes). "
                    f"Usage: {ctx.usage.files} files, {ctx.usage.bytes} bytes, "
                    f"{ctx.usage.remote_requests} requests, depth {ctx.usage.depth}",
                    to_terminal=True,
                )

            # ----------------------------------------------------------------
            # 9. Mark current requirements resolved; clear for next iteration
            # ----------------------------------------------------------------
            frontier.unresolved.clear()
            frontier.symbols.clear()

        # Emit completion metrics
        outcome = ResolutionOutcome.success(rounds=round_num, usage=ctx.usage)
        self._emit(
            "resolver_resolution_complete",
            repository=repository_id,
            commit=commit_sha,
            rounds=round_num,
            **ctx.metrics_snapshot(),
        )
        pipeline_logger.log_pipeline(
            f"[Resolver] Frontier resolution complete after {round_num} rounds. "
            f"Usage: {ctx.usage.snapshot()}",
            to_terminal=True,
        )
        return outcome

    # ------------------------------------------------------------------
    # Synchronous entry-point
    # ------------------------------------------------------------------

    def resolve_sync(
        self,
        repository_id: str,
        commit_sha: str,
        requirements: Sequence[ResolutionRequirement],
        *,
        context: ResolutionContext | None = None,
    ) -> ResolutionOutcome:
        """Synchronously resolve requirements.

        Safe to call from a running event loop (runs the coroutine in a
        dedicated thread so it does not block the caller's loop).

        Returns the :class:`ResolutionOutcome` from the async resolve call.
        """
        coro = self.resolve(
            repository_id, commit_sha, requirements, context=context
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

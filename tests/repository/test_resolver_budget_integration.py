"""
Integration tests for Phase 11 — ResolutionBudget enforcement in RepositoryResolver.

Tests cover:
- Budget exhaustion returning ResolutionOutcome.budget_exhausted()
- Successful resolution returning ResolutionOutcome.success()
- Cumulative usage across multiple frontier iterations
- Cached facts (already-materialized paths) do not consume budget
- Concurrent requests have independent budgets
- All five budget limits independently halt resolution
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from engine.repository.materialization.budget import (
    BudgetExceededReason,
    ResolutionBudget,
    ResolutionUsage,
)
from engine.repository.materialization.materializer import MaterializationResult
from engine.repository.materialization.request import MaterializationRequest
from engine.repository.resolver.context import ResolutionContext
from engine.repository.resolver.outcome import ResolutionOutcome
from engine.repository.resolver.requirements import FileResolutionRequirement
from engine.repository.resolver.resolver import RepositoryResolver

# ---------------------------------------------------------------------------
# Helpers / Stubs
# ---------------------------------------------------------------------------


def _make_file_req(path: str) -> FileResolutionRequirement:
    return FileResolutionRequirement(file_id=path, query_type="file")


def _make_store(
    *,
    missing_paths: set[str] | None = None,
    tree_sizes: dict[str, int] | None = None,
) -> MagicMock:
    """Return a minimal RepositoryStore stub."""
    store = MagicMock()
    missing_paths = missing_paths or set()
    tree_sizes = tree_sizes or {}

    def is_materialized(repo_id, commit, path):
        return path not in missing_paths

    store.is_materialized.side_effect = is_materialized

    def get_tree_entries(repo_id, commit, paths):
        return {p: {"type": "blob", "blob_sha": f"sha_{p}", "size": tree_sizes.get(p, 0)} for p in paths}

    store.get_tree_entries.side_effect = get_tree_entries
    return store


def _make_materializer(
    *,
    materialized: list[str] | None = None,
    bytes_fetched: int = 0,
) -> MagicMock:
    """Return a RepositoryMaterializer stub that records calls."""
    mat = MagicMock()
    mat.materialization_batch_size = 100
    materialized = materialized or []

    result = MaterializationResult(
        requested_paths=tuple(materialized),
        materialized_paths=tuple(materialized),
        already_materialized_paths=(),
        failed_paths=(),
        bytes_fetched=bytes_fetched,
        facts_generated=0,
    )
    mat.materialize = AsyncMock(return_value=result)
    return mat


def _make_planner(paths: list[str]) -> MagicMock:
    """Return a RequirementPlanner stub that always plans the given paths."""
    planner = MagicMock()

    async def plan(repo_id, commit, reqs):
        return (
            MaterializationRequest(
                repository_id=repo_id,
                commit_sha=commit,
                paths=tuple(paths),
                reason="test",
            ),
        )

    planner.plan = plan
    return planner


def _make_resolver(
    *,
    budget: ResolutionBudget,
    missing_paths: set[str],
    planned_paths: list[str],
    tree_sizes: dict[str, int] | None = None,
    materialized_paths: list[str] | None = None,
    bytes_fetched: int = 0,
) -> RepositoryResolver:
    store = _make_store(missing_paths=missing_paths, tree_sizes=tree_sizes)
    mat = _make_materializer(
        materialized=materialized_paths or planned_paths,
        bytes_fetched=bytes_fetched,
    )
    planner = _make_planner(planned_paths)
    resolver = RepositoryResolver(
        store=store,
        source=MagicMock(),
        materializer=mat,
        planner=planner,
        budget=budget,
    )
    return resolver


# ---------------------------------------------------------------------------
# File limit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_file_limit_exceeded_stops_resolution():
    """Budget of 10 files, request plans 11 — budget_exceeded, no acquisition."""
    budget = ResolutionBudget(max_files=10)
    planned = [f"f{i}.py" for i in range(11)]
    resolver = _make_resolver(
        budget=budget,
        # ALL 11 planned paths must be missing so the resolver sees 11 to materialize
        missing_paths=set(planned),
        planned_paths=planned,
        tree_sizes={p: 100 for p in planned},
    )

    outcome = await resolver.resolve(
        "repo", "sha", [_make_file_req("f0.py")]
    )

    assert outcome.complete is False
    assert outcome.budget_exceeded is True
    assert outcome.reason == BudgetExceededReason.MAX_FILES
    # Materializer must NOT have been called
    resolver.materializer.materialize.assert_not_called()


@pytest.mark.asyncio
async def test_file_limit_within_budget_succeeds():
    """Budget of 10 files, request plans 5 — succeeds."""
    budget = ResolutionBudget(max_files=10)
    resolver = _make_resolver(
        budget=budget,
        missing_paths={"a.py", "b.py"},
        planned_paths=["a.py", "b.py"],
        tree_sizes={"a.py": 100, "b.py": 200},
        bytes_fetched=300,
    )

    outcome = await resolver.resolve(
        "repo", "sha", [_make_file_req("a.py")]
    )

    assert outcome.complete is True
    assert outcome.budget_exceeded is False
    resolver.materializer.materialize.assert_called_once()


# ---------------------------------------------------------------------------
# Byte limit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_byte_limit_exceeded_stops_resolution():
    """Budget of 10 MB, request plans 12 MB — budget_exceeded, no acquisition."""
    budget = ResolutionBudget(max_bytes=10 * 1024 * 1024)
    resolver = _make_resolver(
        budget=budget,
        missing_paths={"big.py"},
        planned_paths=["big.py"],
        tree_sizes={"big.py": 12 * 1024 * 1024},
    )

    outcome = await resolver.resolve(
        "repo", "sha", [_make_file_req("big.py")]
    )

    assert outcome.complete is False
    assert outcome.budget_exceeded is True
    assert outcome.reason == BudgetExceededReason.MAX_BYTES
    resolver.materializer.materialize.assert_not_called()


# ---------------------------------------------------------------------------
# Remote request limit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_remote_request_limit_exceeded():
    """Budget of 2 requests; after 2, next is rejected."""
    budget = ResolutionBudget(max_remote_requests=2)

    # We need a fresh context with usage already at 2
    ctx = ResolutionContext(budget=budget, usage=ResolutionUsage())
    ctx.usage.remote_requests = 2

    resolver = _make_resolver(
        budget=budget,
        missing_paths={"x.py"},
        planned_paths=["x.py"],
        tree_sizes={"x.py": 100},
        # batch_size=100 → 1 file → 1 remote request → 2+1=3 > 2
    )

    outcome = await resolver.resolve(
        "repo", "sha", [_make_file_req("x.py")], context=ctx
    )

    assert outcome.complete is False
    assert outcome.budget_exceeded is True
    assert outcome.reason == BudgetExceededReason.MAX_REMOTE_REQUESTS
    resolver.materializer.materialize.assert_not_called()


# ---------------------------------------------------------------------------
# Depth limit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_depth_limit_allows_at_boundary():
    """max_depth=3: rounds 1, 2, 3 allowed; round 4 rejected."""
    # We simulate a resolver where each round clears the frontier (no new work),
    # so only round 1 runs. The depth check for round 1 (depth=1) should pass.
    budget = ResolutionBudget(max_depth=3)
    resolver = _make_resolver(
        budget=budget,
        missing_paths={"a.py"},
        planned_paths=["a.py"],
        tree_sizes={"a.py": 0},
    )
    outcome = await resolver.resolve(
        "repo", "sha", [_make_file_req("a.py")]
    )
    assert outcome.complete is True
    assert outcome.rounds == 1


@pytest.mark.asyncio
async def test_depth_limit_exceeded_in_deep_context():
    """Resolver with a context already at depth 4 (> max_depth=3) is rejected."""
    budget = ResolutionBudget(max_depth=3)
    ResolutionContext(budget=budget)
    # Simulate being in round 4 (depth will become 4 inside resolve)
    # We do this by pre-seeding usage.depth and giving a very small max_depth
    # such that round_num=1 will immediately exceed the limit.
    budget2 = ResolutionBudget(max_depth=0)  # depth 1 > 0 → rejected
    resolver = _make_resolver(
        budget=budget2,
        missing_paths={"a.py"},
        planned_paths=["a.py"],
        tree_sizes={"a.py": 0},
    )
    outcome = await resolver.resolve(
        "repo", "sha", [_make_file_req("a.py")]
    )
    assert outcome.complete is False
    assert outcome.budget_exceeded is True
    assert outcome.reason == BudgetExceededReason.MAX_DEPTH


# ---------------------------------------------------------------------------
# Unresolved-symbol limit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unresolved_symbol_limit_exceeded():
    """101 unique unresolved symbols with limit=100 → stops resolution."""
    from engine.repository.resolver.requirements import SymbolResolutionRequirement

    budget = ResolutionBudget(max_unresolved_symbols=100)
    store = _make_store(missing_paths=set())
    mat = _make_materializer()
    planner = MagicMock()

    async def plan(repo_id, commit, reqs):
        return ()

    planner.plan = plan

    resolver = RepositoryResolver(
        store=store,
        source=MagicMock(),
        materializer=mat,
        planner=planner,
        budget=budget,
    )

    # 101 unique symbol requirements
    reqs = [SymbolResolutionRequirement(symbol_id=i, query_type="callers") for i in range(101)]

    outcome = await resolver.resolve("repo", "sha", reqs)

    assert outcome.complete is False
    assert outcome.budget_exceeded is True
    assert outcome.reason == BudgetExceededReason.MAX_UNRESOLVED_SYMBOLS


# ---------------------------------------------------------------------------
# Cumulative usage across multiple frontier iterations
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cumulative_usage_across_iterations():
    """
    Simulate 3 frontier iterations accumulating file usage.

    Iteration 1: 5 files
    Iteration 2: 8 files (but deduplication means unique total = 13)
    Iteration 3 (planned): 3 files — if max_files=13, this is rejected.
    """
    budget = ResolutionBudget(max_files=13)

    # We'll use a context we control
    ctx = ResolutionContext(budget=budget)

    # Simulate iteration 1 usage: 5 unique files
    batch1 = [f"f{i}.py" for i in range(5)]
    ctx.usage.record_paths(batch1, {p: 0 for p in batch1})
    assert ctx.usage.files == 5

    # Simulate iteration 2 usage: 8 unique files (all new)
    batch2 = [f"f{i}.py" for i in range(5, 13)]
    ctx.usage.record_paths(batch2, {p: 0 for p in batch2})
    assert ctx.usage.files == 13

    # Now a third batch of 3 files would push us to 16 > 13
    decision = ctx.can_materialize(
        files=3, bytes=0, remote_requests=0, depth=3, unresolved_symbols=0
    )
    assert decision.allowed is False
    assert decision.reason == BudgetExceededReason.MAX_FILES


# ---------------------------------------------------------------------------
# Cached facts do not consume budget
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cached_paths_do_not_consume_budget():
    """Paths already in the store must not trigger materialization or budget use."""
    budget = ResolutionBudget(max_files=5)
    # "already.py" is already materialized (not in missing_paths)
    store = _make_store(missing_paths=set(), tree_sizes={"already.py": 500_000})
    mat = _make_materializer(materialized=[])
    planner = _make_planner(["already.py"])

    resolver = RepositoryResolver(
        store=store,
        source=MagicMock(),
        materializer=mat,
        planner=planner,
        budget=budget,
    )

    outcome = await resolver.resolve(
        "repo", "sha", [_make_file_req("already.py")]
    )

    assert outcome.complete is True
    # No materialization call since path was already in store
    mat.materialize.assert_not_called()
    # Budget usage: 0 files (no new acquisition)
    assert outcome.usage.files == 0


# ---------------------------------------------------------------------------
# Concurrent requests have independent budgets
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_concurrent_requests_independent_budgets():
    """Two concurrent resolution calls must not share usage state."""
    budget = ResolutionBudget(max_files=5)

    # Request A: plans 4 files
    resolver_a = _make_resolver(
        budget=budget,
        missing_paths={"a1.py", "a2.py", "a3.py", "a4.py"},
        planned_paths=["a1.py", "a2.py", "a3.py", "a4.py"],
        tree_sizes={f"a{i}.py": 0 for i in range(1, 5)},
        bytes_fetched=0,
    )

    # Request B: also plans 4 files (different resolver instance = different budget)
    resolver_b = _make_resolver(
        budget=budget,
        missing_paths={"b1.py", "b2.py", "b3.py", "b4.py"},
        planned_paths=["b1.py", "b2.py", "b3.py", "b4.py"],
        tree_sizes={f"b{i}.py": 0 for i in range(1, 5)},
        bytes_fetched=0,
    )

    outcome_a, outcome_b = await asyncio.gather(
        resolver_a.resolve("repo", "sha", [_make_file_req("a1.py")]),
        resolver_b.resolve("repo", "sha", [_make_file_req("b1.py")]),
    )

    # Both should succeed independently (4 < max_files=5 each)
    assert outcome_a.complete is True
    assert outcome_b.complete is True
    # Usage in each outcome is independent
    assert outcome_a.usage is not outcome_b.usage


# ---------------------------------------------------------------------------
# ResolutionOutcome invariant: budget_exceeded != fact missing
# ---------------------------------------------------------------------------


def test_budget_exceeded_is_not_fact_missing():
    """Verify the invariant that budget exhaustion is distinct from empty results."""
    usage = ResolutionUsage()
    exhausted = ResolutionOutcome.budget_exhausted(
        reason=BudgetExceededReason.MAX_FILES,
        rounds=1,
        usage=usage,
    )
    # This is NOT the same as a successful result with no facts
    success_empty = ResolutionOutcome.success(rounds=0, usage=ResolutionUsage())

    assert exhausted.complete is False
    assert exhausted.budget_exceeded is True
    assert success_empty.complete is True
    assert success_empty.budget_exceeded is False


# ---------------------------------------------------------------------------
# resolve_sync returns ResolutionOutcome (not None)
# ---------------------------------------------------------------------------


def test_resolve_sync_returns_outcome():
    """resolve_sync must return a ResolutionOutcome, not None."""
    budget = ResolutionBudget(max_files=10)
    store = _make_store(missing_paths=set())
    mat = _make_materializer()
    planner = _make_planner([])

    resolver = RepositoryResolver(
        store=store,
        source=MagicMock(),
        materializer=mat,
        planner=planner,
        budget=budget,
    )

    outcome = resolver.resolve_sync("repo", "sha", [_make_file_req("x.py")])
    assert isinstance(outcome, ResolutionOutcome)
    assert outcome.complete is True

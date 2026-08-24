"""
Unit tests for Phase 11 resolution budget model.

Tests cover:
- ResolutionBudget construction and defaults
- ResolutionUsage deduplication (files, symbols)
- ResolutionContext.can_materialize() for each of the 5 limit types
- Batch accounting (cumulative across batches)
- Independent budget state per-request (no shared mutable global state)
- BudgetDecision and BudgetExceededReason correctness
- ResolutionOutcome named constructors and metrics_snapshot
"""

import pytest

from engine.repository.materialization.budget import (
    BudgetExceededReason,
    MaterializationBudget,  # alias
    MaterializationBudgetExceeded,
    ResolutionBudget,
    ResolutionUsage,
)
from engine.repository.resolver.context import ResolutionContext
from engine.repository.resolver.outcome import ResolutionOutcome

# ---------------------------------------------------------------------------
# ResolutionBudget
# ---------------------------------------------------------------------------


class TestResolutionBudget:
    def test_defaults(self):
        b = ResolutionBudget()
        assert b.max_files == 500
        assert b.max_bytes == 50 * 1024 * 1024
        assert b.max_remote_requests == 100
        assert b.max_depth == 20
        assert b.max_unresolved_symbols == 1_000

    def test_custom_values(self):
        b = ResolutionBudget(
            max_files=10,
            max_bytes=1_000,
            max_remote_requests=2,
            max_depth=3,
            max_unresolved_symbols=50,
        )
        assert b.max_files == 10
        assert b.max_bytes == 1_000
        assert b.max_remote_requests == 2
        assert b.max_depth == 3
        assert b.max_unresolved_symbols == 50

    def test_immutable(self):
        b = ResolutionBudget()
        with pytest.raises((AttributeError, TypeError)):
            b.max_files = 999  # type: ignore[misc]

    def test_backward_compat_alias(self):
        """MaterializationBudget is an alias for ResolutionBudget."""
        b = MaterializationBudget(max_files=7)
        assert isinstance(b, ResolutionBudget)
        assert b.max_files == 7


# ---------------------------------------------------------------------------
# ResolutionUsage
# ---------------------------------------------------------------------------


class TestResolutionUsage:
    def test_initial_zeros(self):
        u = ResolutionUsage()
        assert u.files == 0
        assert u.bytes == 0
        assert u.remote_requests == 0
        assert u.depth == 0
        assert u.unresolved_symbols == 0

    def test_record_paths_deduplication(self):
        u = ResolutionUsage()
        u.record_paths(["a.py", "b.py"], {"a.py": 100, "b.py": 200})
        assert u.files == 2
        assert u.bytes == 300

        # Record same paths again — should not double-count
        u.record_paths(["a.py", "b.py"], {"a.py": 100, "b.py": 200})
        assert u.files == 2
        assert u.bytes == 300

    def test_record_paths_new_file_after_duplicate(self):
        u = ResolutionUsage()
        u.record_paths(["a.py"], {"a.py": 50})
        u.record_paths(["a.py", "c.py"], {"a.py": 50, "c.py": 150})
        assert u.files == 2
        assert u.bytes == 200  # 50 (a.py) + 150 (c.py)

    def test_record_remote_request(self):
        u = ResolutionUsage()
        u.record_remote_request()
        u.record_remote_request()
        assert u.remote_requests == 2

    def test_record_symbols_deduplication(self):
        """Same symbol IDs across iterations count only once."""
        u = ResolutionUsage()
        # Iteration 1: Foo, Bar
        u.record_symbols(["Foo", "Bar"])
        assert u.unresolved_symbols == 2

        # Iteration 2: Foo (dup), Baz (new)
        u.record_symbols(["Foo", "Baz"])
        assert u.unresolved_symbols == 3  # Foo, Bar, Baz

    def test_snapshot(self):
        u = ResolutionUsage()
        u.record_paths(["x.py"], {"x.py": 42})
        u.record_remote_request()
        u.depth = 2
        snap = u.snapshot()
        assert snap["files"] == 1
        assert snap["bytes"] == 42
        assert snap["remote_requests"] == 1
        assert snap["depth"] == 2
        assert snap["unresolved_symbols"] == 0


# ---------------------------------------------------------------------------
# ResolutionContext — can_materialize()
# ---------------------------------------------------------------------------


class TestResolutionContext:
    def _ctx(self, **budget_kwargs) -> ResolutionContext:
        return ResolutionContext(budget=ResolutionBudget(**budget_kwargs))

    # ---- max_files --------------------------------------------------------

    def test_file_limit_allowed(self):
        ctx = self._ctx(max_files=10)
        decision = ctx.can_materialize(
            files=10, bytes=0, remote_requests=0, depth=1, unresolved_symbols=0
        )
        assert decision.allowed is True
        assert decision.reason is None

    def test_file_limit_exceeded(self):
        ctx = self._ctx(max_files=10)
        decision = ctx.can_materialize(
            files=11, bytes=0, remote_requests=0, depth=1, unresolved_symbols=0
        )
        assert decision.allowed is False
        assert decision.reason == BudgetExceededReason.MAX_FILES

    def test_file_limit_cumulative_exceeded(self):
        """Second batch exceeds cumulative limit."""
        ctx = self._ctx(max_files=10)
        ctx.usage.record_paths(["a.py"] * 8, {f"a_{i}.py": 0 for i in range(8)})
        # Manually set to 8 unique paths
        ctx.usage._materialized_paths = {f"f{i}" for i in range(8)}
        ctx.usage.files = 8

        decision = ctx.can_materialize(
            files=3, bytes=0, remote_requests=0, depth=1, unresolved_symbols=0
        )
        assert decision.allowed is False
        assert decision.reason == BudgetExceededReason.MAX_FILES

    def test_file_limit_cumulative_within_budget(self):
        ctx = self._ctx(max_files=10)
        ctx.usage.files = 8
        decision = ctx.can_materialize(
            files=2, bytes=0, remote_requests=0, depth=1, unresolved_symbols=0
        )
        assert decision.allowed is True

    # ---- max_bytes --------------------------------------------------------

    def test_byte_limit_exceeded(self):
        """Batch exceeds byte limit — no acquisition should occur."""
        ctx = self._ctx(max_bytes=10 * 1024 * 1024)  # 10 MB
        decision = ctx.can_materialize(
            files=1,
            bytes=12 * 1024 * 1024,  # 12 MB
            remote_requests=1,
            depth=1,
            unresolved_symbols=0,
        )
        assert decision.allowed is False
        assert decision.reason == BudgetExceededReason.MAX_BYTES

    def test_byte_limit_allowed(self):
        ctx = self._ctx(max_bytes=10 * 1024 * 1024)
        decision = ctx.can_materialize(
            files=1,
            bytes=9 * 1024 * 1024,
            remote_requests=1,
            depth=1,
            unresolved_symbols=0,
        )
        assert decision.allowed is True

    # ---- max_remote_requests -----------------------------------------------

    def test_remote_request_limit_exceeded(self):
        ctx = self._ctx(max_remote_requests=2)
        ctx.usage.remote_requests = 2
        decision = ctx.can_materialize(
            files=0, bytes=0, remote_requests=1, depth=1, unresolved_symbols=0
        )
        assert decision.allowed is False
        assert decision.reason == BudgetExceededReason.MAX_REMOTE_REQUESTS

    def test_remote_request_limit_boundary(self):
        """After exactly 2 requests, next is rejected."""
        ctx = self._ctx(max_remote_requests=2)
        ctx.usage.remote_requests = 0

        d1 = ctx.can_materialize(files=0, bytes=0, remote_requests=1, depth=1, unresolved_symbols=0)
        assert d1.allowed is True
        ctx.usage.remote_requests = 1

        d2 = ctx.can_materialize(files=0, bytes=0, remote_requests=1, depth=1, unresolved_symbols=0)
        assert d2.allowed is True
        ctx.usage.remote_requests = 2

        d3 = ctx.can_materialize(files=0, bytes=0, remote_requests=1, depth=1, unresolved_symbols=0)
        assert d3.allowed is False
        assert d3.reason == BudgetExceededReason.MAX_REMOTE_REQUESTS

    # ---- max_depth ---------------------------------------------------------

    def test_depth_allowed_at_boundary(self):
        """depth == max_depth is allowed (inclusive)."""
        ctx = self._ctx(max_depth=3)
        for d in (0, 1, 2, 3):
            decision = ctx.can_materialize(
                files=0, bytes=0, remote_requests=0, depth=d, unresolved_symbols=0
            )
            assert decision.allowed is True, f"depth={d} should be allowed"

    def test_depth_exceeded_above_boundary(self):
        """depth > max_depth is rejected."""
        ctx = self._ctx(max_depth=3)
        decision = ctx.can_materialize(
            files=0, bytes=0, remote_requests=0, depth=4, unresolved_symbols=0
        )
        assert decision.allowed is False
        assert decision.reason == BudgetExceededReason.MAX_DEPTH

    # ---- max_unresolved_symbols -------------------------------------------

    def test_unresolved_symbol_limit_exceeded(self):
        ctx = self._ctx(max_unresolved_symbols=100)
        decision = ctx.can_materialize(
            files=0, bytes=0, remote_requests=0, depth=1, unresolved_symbols=101
        )
        assert decision.allowed is False
        assert decision.reason == BudgetExceededReason.MAX_UNRESOLVED_SYMBOLS

    def test_unresolved_symbol_limit_at_boundary(self):
        ctx = self._ctx(max_unresolved_symbols=100)
        decision = ctx.can_materialize(
            files=0, bytes=0, remote_requests=0, depth=1, unresolved_symbols=100
        )
        assert decision.allowed is True

    # ---- remaining capacity ------------------------------------------------

    def test_remaining_files(self):
        ctx = self._ctx(max_files=20)
        ctx.usage.files = 5
        assert ctx.remaining_files == 15

    def test_remaining_bytes(self):
        ctx = self._ctx(max_bytes=1_000)
        ctx.usage.bytes = 300
        assert ctx.remaining_bytes == 700

    def test_remaining_remote_requests(self):
        ctx = self._ctx(max_remote_requests=10)
        ctx.usage.remote_requests = 7
        assert ctx.remaining_remote_requests == 3

    # ---- metrics_snapshot --------------------------------------------------

    def test_metrics_snapshot_structure(self):
        ctx = self._ctx(max_files=5, max_bytes=1000)
        snap = ctx.metrics_snapshot()
        assert "resolution_budget" in snap
        assert "resolution_usage" in snap
        assert snap["resolution_budget"]["max_files"] == 5
        assert snap["resolution_budget"]["max_bytes"] == 1000
        assert snap["resolution_usage"]["files"] == 0


# ---------------------------------------------------------------------------
# Batch accounting tests (cumulative budget)
# ---------------------------------------------------------------------------


class TestBatchAccounting:
    def test_cumulative_across_batches(self):
        """Budget is cumulative — remaining capacity decreases across batches."""
        ctx = ResolutionContext(
            budget=ResolutionBudget(max_files=20, max_bytes=5 * 1024 * 1024, max_remote_requests=2)
        )

        # Batch 1: 15 files, 4 MB, 1 request
        b1 = ctx.can_materialize(
            files=15, bytes=4 * 1024 * 1024, remote_requests=1, depth=1, unresolved_symbols=0
        )
        assert b1.allowed is True
        ctx.usage.files += 15
        ctx.usage.bytes += 4 * 1024 * 1024
        ctx.usage.remote_requests += 1

        assert ctx.remaining_files == 5
        assert ctx.remaining_remote_requests == 1

        # Batch 2: 10 files — exceeds remaining (5)
        b2 = ctx.can_materialize(
            files=10, bytes=0, remote_requests=1, depth=1, unresolved_symbols=0
        )
        assert b2.allowed is False
        assert b2.reason == BudgetExceededReason.MAX_FILES

    def test_batch_within_remaining_passes(self):
        ctx = ResolutionContext(
            budget=ResolutionBudget(max_files=20, max_bytes=5 * 1024 * 1024, max_remote_requests=2)
        )
        ctx.usage.files = 15
        ctx.usage.bytes = 4 * 1024 * 1024
        ctx.usage.remote_requests = 1

        b = ctx.can_materialize(
            files=5, bytes=1 * 1024 * 1024, remote_requests=1, depth=1, unresolved_symbols=0
        )
        assert b.allowed is True


# ---------------------------------------------------------------------------
# Independent budget state per request
# ---------------------------------------------------------------------------


class TestBudgetIsolation:
    def test_two_requests_independent(self):
        """Each request gets its own ResolutionContext with zero usage."""
        ctx_a = ResolutionContext(budget=ResolutionBudget(max_files=10))
        ctx_b = ResolutionContext(budget=ResolutionBudget(max_files=10))

        ctx_a.usage.files = 9

        # ctx_b starts at zero regardless of ctx_a's state
        assert ctx_b.usage.files == 0
        assert ctx_a.usage.files == 9

    def test_no_shared_mutable_state(self):
        """ResolutionUsage instances must not share internal sets."""
        u1 = ResolutionUsage()
        u2 = ResolutionUsage()

        u1.record_paths(["a.py"], {"a.py": 100})
        assert u2.files == 0
        assert u1.files == 1

        u1.record_symbols(["SymA"])
        assert u2.unresolved_symbols == 0


# ---------------------------------------------------------------------------
# ResolutionOutcome
# ---------------------------------------------------------------------------


class TestResolutionOutcome:
    def test_success_outcome(self):
        usage = ResolutionUsage()
        usage.files = 5
        outcome = ResolutionOutcome.success(rounds=3, usage=usage)
        assert outcome.complete is True
        assert outcome.budget_exceeded is False
        assert outcome.reason is None
        assert outcome.rounds == 3
        assert outcome.usage.files == 5

    def test_budget_exhausted_outcome(self):
        usage = ResolutionUsage()
        usage.bytes = 12 * 1024 * 1024
        outcome = ResolutionOutcome.budget_exhausted(
            reason=BudgetExceededReason.MAX_BYTES,
            rounds=1,
            usage=usage,
        )
        assert outcome.complete is False
        assert outcome.budget_exceeded is True
        assert outcome.reason == BudgetExceededReason.MAX_BYTES
        assert outcome.rounds == 1

    def test_metrics_snapshot(self):
        usage = ResolutionUsage()
        usage.files = 3
        outcome = ResolutionOutcome.budget_exhausted(
            reason=BudgetExceededReason.MAX_FILES,
            rounds=2,
            usage=usage,
        )
        snap = outcome.metrics_snapshot()
        assert snap["complete"] is False
        assert snap["budget_exceeded"] is True
        assert snap["budget_exceeded_reason"] == "max_files"
        assert snap["rounds"] == 2
        assert snap["resolution_usage"]["files"] == 3

    def test_budget_exceeded_distinct_from_empty_result(self):
        """budget_exceeded=True does NOT mean 'fact does not exist'."""
        usage = ResolutionUsage()
        outcome = ResolutionOutcome.budget_exhausted(
            reason=BudgetExceededReason.MAX_DEPTH,
            rounds=5,
            usage=usage,
        )
        # The outcome explicitly encodes the budget situation, not an empty result
        assert outcome.budget_exceeded is True
        assert outcome.complete is False
        # A successful outcome with zero facts is a different state
        empty_success = ResolutionOutcome.success(rounds=0, usage=ResolutionUsage())
        assert empty_success.complete is True
        assert empty_success.budget_exceeded is False


# ---------------------------------------------------------------------------
# BudgetExceededReason string values (for machine-readable observability)
# ---------------------------------------------------------------------------


class TestBudgetExceededReasonValues:
    def test_reason_values(self):
        assert BudgetExceededReason.MAX_FILES.value == "max_files"
        assert BudgetExceededReason.MAX_BYTES.value == "max_bytes"
        assert BudgetExceededReason.MAX_REMOTE_REQUESTS.value == "max_remote_requests"
        assert BudgetExceededReason.MAX_DEPTH.value == "max_depth"
        assert BudgetExceededReason.MAX_UNRESOLVED_SYMBOLS.value == "max_unresolved_symbols"


# ---------------------------------------------------------------------------
# Legacy MaterializationBudgetExceeded still importable
# ---------------------------------------------------------------------------


class TestLegacyCompatibility:
    def test_exception_importable(self):
        exc = MaterializationBudgetExceeded("test")
        assert str(exc) == "test"

    def test_exception_is_exception(self):
        with pytest.raises(MaterializationBudgetExceeded):
            raise MaterializationBudgetExceeded("legacy path")

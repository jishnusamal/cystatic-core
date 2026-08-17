from __future__ import annotations

from dataclasses import dataclass

from engine.repository.materialization.budget import (
    BudgetExceededReason,
    ResolutionUsage,
)


@dataclass(frozen=True)
class ResolutionOutcome:
    """Immutable result of a :meth:`RepositoryResolver.resolve` call.

    ``complete=True`` means all requirements were satisfied within the
    allocated budget.

    ``complete=False`` means resolution stopped before all requirements were
    satisfied.  Inspect ``budget_exceeded`` and ``reason`` to understand why.

    Critical invariant::

        budget_exceeded=True  ≠  "fact does not exist"

    Phase 12 consumes this signal to decide whether to fall back to the full
    ``RepositoryIndexer`` without changing the compiler architecture.

    Attributes
    ----------
    complete:
        Whether resolution finished without hitting a budget limit.
    budget_exceeded:
        True when a budget limit caused resolution to stop.
    reason:
        Which specific limit was exceeded (None when ``complete=True``).
    rounds:
        Number of frontier iterations that completed before stopping.
    usage:
        Snapshot of resource consumption at the point resolution ended.
    """

    complete: bool
    budget_exceeded: bool = False
    reason: BudgetExceededReason | None = None
    rounds: int = 0
    usage: ResolutionUsage | None = None

    # ------------------------------------------------------------------
    # Named constructors
    # ------------------------------------------------------------------

    @classmethod
    def success(cls, rounds: int, usage: ResolutionUsage) -> "ResolutionOutcome":
        """Create a successful (within-budget) outcome."""
        return cls(complete=True, rounds=rounds, usage=usage)

    @classmethod
    def budget_exhausted(
        cls,
        reason: BudgetExceededReason,
        rounds: int,
        usage: ResolutionUsage,
    ) -> "ResolutionOutcome":
        """Create a budget-exceeded outcome for Phase 12 to consume."""
        return cls(
            complete=False,
            budget_exceeded=True,
            reason=reason,
            rounds=rounds,
            usage=usage,
        )

    # ------------------------------------------------------------------
    # Observability
    # ------------------------------------------------------------------

    @property
    def fallback_required(self) -> bool:
        """True when this outcome signals that full indexing is preferred.

        Semantic alias for ``budget_exceeded``.  Phase 12 consumers should
        prefer this name; Phase 11 code that reads ``budget_exceeded``
        continues to work without modification.
        """
        return self.budget_exceeded

    def metrics_snapshot(self) -> dict:
        """Return a machine-readable summary suitable for structured logging."""
        snap: dict = {
            "complete": self.complete,
            "budget_exceeded": self.budget_exceeded,
            "fallback_required": self.fallback_required,
            "budget_exceeded_reason": self.reason.value if self.reason else None,
            "rounds": self.rounds,
        }
        if self.usage is not None:
            snap["resolution_usage"] = self.usage.snapshot()
        return snap


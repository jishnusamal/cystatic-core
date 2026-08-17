from __future__ import annotations

import math
from dataclasses import dataclass, field

from engine.repository.materialization.budget import (
    BudgetDecision,
    BudgetExceededReason,
    ResolutionBudget,
    ResolutionUsage,
)


@dataclass
class ResolutionContext:
    """Request-scoped state for a single lazy resolution operation.

    Bundles the immutable budget limits with the mutable running usage so
    that the resolver loop has a single object to consult for all budget
    decisions.

    Two concurrent analysis requests must never share a ``ResolutionContext``.

    Ownership::

        Analysis Request
               │
               ▼
        ResolutionContext (budget + usage)
               │
               ▼
        RepositoryResolver
               │
               ▼
        RepositoryMaterializer
    """

    budget: ResolutionBudget
    usage: ResolutionUsage = field(default_factory=ResolutionUsage)

    # Optional observability / tracing fields.
    request_id: str | None = None
    repository_id: str | None = None
    commit_sha: str | None = None

    # ------------------------------------------------------------------
    # Pre-materialization decision
    # ------------------------------------------------------------------

    def can_materialize(
        self,
        *,
        files: int,
        bytes: int,
        remote_requests: int,
        depth: int,
        unresolved_symbols: int,
    ) -> BudgetDecision:
        """Return a structured decision before any acquisition takes place.

        All checks compare *remaining* capacity (limits minus current usage)
        against the planned batch so that the budget is cumulative across
        multiple frontier iterations.

        The check order follows the implementation plan:

        1. ``max_files``
        2. ``max_bytes``
        3. ``max_remote_requests``
        4. ``max_depth``
        5. ``max_unresolved_symbols``

        Only the first exceeded limit is reported; the caller stops
        immediately and does not proceed to further checks.
        """
        if self.usage.files + files > self.budget.max_files:
            return BudgetDecision(allowed=False, reason=BudgetExceededReason.MAX_FILES)
        if self.usage.bytes + bytes > self.budget.max_bytes:
            return BudgetDecision(allowed=False, reason=BudgetExceededReason.MAX_BYTES)
        if self.usage.remote_requests + remote_requests > self.budget.max_remote_requests:
            return BudgetDecision(allowed=False, reason=BudgetExceededReason.MAX_REMOTE_REQUESTS)
        if depth > self.budget.max_depth:
            return BudgetDecision(allowed=False, reason=BudgetExceededReason.MAX_DEPTH)
        if unresolved_symbols > self.budget.max_unresolved_symbols:
            return BudgetDecision(allowed=False, reason=BudgetExceededReason.MAX_UNRESOLVED_SYMBOLS)
        return BudgetDecision(allowed=True)

    # ------------------------------------------------------------------
    # Convenience properties (remaining capacity)
    # ------------------------------------------------------------------

    @property
    def remaining_files(self) -> int:
        return self.budget.max_files - self.usage.files

    @property
    def remaining_bytes(self) -> int:
        return self.budget.max_bytes - self.usage.bytes

    @property
    def remaining_remote_requests(self) -> int:
        return self.budget.max_remote_requests - self.usage.remote_requests

    # ------------------------------------------------------------------
    # Helpers for pre-flight estimation
    # ------------------------------------------------------------------

    def estimate_remote_requests(self, num_files: int, batch_size: int) -> int:
        """Return the number of provider calls a batch of *num_files* would require."""
        if num_files == 0:
            return 0
        return math.ceil(num_files / batch_size)

    # ------------------------------------------------------------------
    # Metrics snapshot
    # ------------------------------------------------------------------

    def metrics_snapshot(self) -> dict:
        """Return a machine-readable snapshot of limits and usage."""
        return {
            "resolution_budget": {
                "max_files": self.budget.max_files,
                "max_bytes": self.budget.max_bytes,
                "max_remote_requests": self.budget.max_remote_requests,
                "max_depth": self.budget.max_depth,
                "max_unresolved_symbols": self.budget.max_unresolved_symbols,
            },
            "resolution_usage": self.usage.snapshot(),
        }

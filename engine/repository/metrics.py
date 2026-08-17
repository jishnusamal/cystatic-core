from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RepositoryMaterializationMetrics:
    """Request-scoped repository materialization metrics."""

    repository_files: int = 0
    repository_bytes: int = 0

    _materialized_paths: set[str] = field(default_factory=set)
    materialized_bytes: int = 0

    repository_acquisition_ms: float = 0.0
    repository_indexing_ms: float = 0.0

    facts_generated: int = 0
    blob_cache_hits: int = 0
    blob_cache_misses: int = 0
    indexed_files: int = 0

    requested_files: int = 0
    deduplicated_files: int = 0
    already_materialized_files: int = 0
    files_fetched: int = 0
    bytes_fetched: int = 0
    remote_requests: int = 0
    duration: float = 0.0
    reason: str = ""

    # ------------------------------------------------------------------
    # Phase 11 — Resolution budget observability
    #
    # These fields are populated by the resolver after each resolution
    # operation.  They are deliberately typed as ``Any`` / ``dict`` so that
    # downstream code that reads metrics snapshots does not need to import
    # budget types directly.
    # ------------------------------------------------------------------

    resolution_budget: dict[str, Any] | None = None
    """Configured budget limits for this request (set by RepositoryResolver)."""

    resolution_usage: dict[str, Any] | None = None
    """Actual resource consumption recorded at resolution completion."""

    budget_exceeded: bool = False
    """True when a budget limit caused lazy resolution to stop early."""

    budget_exceeded_reason: str | None = None
    """Which specific limit was exceeded (None if resolution completed normally)."""

    def set_repository_size(
        self,
        *,
        files: int,
        bytes: int,
    ) -> None:
        self.repository_files = files
        self.repository_bytes = bytes

    def record_file(
        self,
        *,
        path: str,
        size: int = 0,
    ) -> None:
        # Materialization is counted by unique repository path.
        if path in self._materialized_paths:
            return

        self._materialized_paths.add(path)
        self.materialized_bytes += size

    def record_resolution_outcome(self, outcome: Any) -> None:
        """Populate budget observability fields from a ResolutionOutcome.

        Accepts ``Any`` to avoid a circular import with the resolver package.
        The caller (RepositoryResolver or RepositoryView) passes the outcome
        object; this method extracts what it needs via duck-typing.
        """
        if outcome is None:
            return
        self.budget_exceeded = bool(getattr(outcome, "budget_exceeded", False))
        reason = getattr(outcome, "reason", None)
        self.budget_exceeded_reason = reason.value if reason is not None else None
        usage = getattr(outcome, "usage", None)
        if usage is not None and hasattr(usage, "snapshot"):
            self.resolution_usage = usage.snapshot()

    @property
    def materialized_files(self) -> int:
        return len(self._materialized_paths)

    @property
    def materialization_ratio(self) -> float:
        if self.repository_files == 0:
            return 0.0

        return self.materialized_files / self.repository_files

    @property
    def materialization_percent(self) -> float:
        return self.materialization_ratio * 100

    @property
    def materialization_bytes_ratio(self) -> float:
        if self.repository_bytes == 0:
            return 0.0

        return self.materialized_bytes / self.repository_bytes

    @property
    def materialization_bytes_percent(self) -> float:
        return self.materialization_bytes_ratio * 100

    def snapshot(self) -> dict[str, int | float | str | bool | dict | None]:
        snap: dict[str, Any] = {
            "repository_acquisition_ms": round(self.repository_acquisition_ms, 3),
            "repository_indexing_ms": round(self.repository_indexing_ms, 3),
            "repository_files": self.repository_files,
            "materialized_files": self.materialized_files,
            "materialization_ratio": round(self.materialization_ratio, 6),
            "materialization_percent": round(self.materialization_percent, 4),
            "repository_bytes": self.repository_bytes,
            "materialized_bytes": self.materialized_bytes,
            "materialization_bytes_ratio": round(self.materialization_bytes_ratio, 6),
            "materialization_bytes_percent": round(
                self.materialization_bytes_percent, 4
            ),
            "facts_generated": self.facts_generated,
            "blob_cache_hits": self.blob_cache_hits,
            "blob_cache_misses": self.blob_cache_misses,
            "indexed_files": self.indexed_files,
            "requested_files": self.requested_files,
            "deduplicated_files": self.deduplicated_files,
            "already_materialized_files": self.already_materialized_files,
            "files_fetched": self.files_fetched,
            "bytes_fetched": self.bytes_fetched,
            "remote_requests": self.remote_requests,
            "duration": round(self.duration, 3),
            "reason": self.reason,
            # Phase 11 budget observability
            "resolution_budget": self.resolution_budget,
            "resolution_usage": self.resolution_usage,
            "budget_exceeded": self.budget_exceeded,
            "budget_exceeded_reason": self.budget_exceeded_reason,
        }
        return snap

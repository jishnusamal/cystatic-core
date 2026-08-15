"""Core runtime utilities for Factor analysis runs.

Canonical location. Manages run IDs, log directories, and execution context.
"""

from __future__ import annotations

import secrets
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from core.logging import LogManager

# ---------------------------------------------------------------------------
# Architecture invariant guard
# ---------------------------------------------------------------------------
# When set to True in a context, any attempt to construct legacy objects
# (RepositoryGraph, RepositoryModel, GraphPatcher) will raise a RuntimeError.
# The production PR-analysis path sets this to True before running so that
# accidental regressions fail loudly rather than silently recreating the
# 3.4 GB memory problem.
PREVENT_LEGACY_ARCHITECTURE: ContextVar[bool] = ContextVar(
    "prevent_legacy_architecture", default=False
)


def assert_new_architecture(class_name: str) -> None:
    """Raise RuntimeError if legacy architecture is forbidden in the current context."""
    if PREVENT_LEGACY_ARCHITECTURE.get():
        raise RuntimeError(
            f"[Architecture Assertion] Attempt to construct '{class_name}' detected "
            f"in a context that requires the new fact-based architecture. "
            f"Legacy objects (RepositoryGraph, RepositoryModel, GraphPatcher) must "
            f"not be created during PR analysis. "
            f"See engine/pipeline/pipeline.py and PREVENT_LEGACY_ARCHITECTURE."
        )


def generate_run_id(started_at: datetime | None = None) -> str:
    """Generate a unique, filesystem-safe run identifier.

    Format: run-YYYYMMDD-HHMMSS-<6 hex chars>
    Example: run-20260722-104155-8c9f2a
    """
    if started_at is None:
        started_at = datetime.now()
    timestamp_str = started_at.strftime("%Y%m%d-%H%M%S")
    random_suffix = secrets.token_hex(3)
    return f"run-{timestamp_str}-{random_suffix}"


@dataclass(frozen=True)
class RunContext:
    """Immutable execution context for a single Factor analysis run."""

    run_id: str
    started_at: datetime
    log_dir: Path
    log_manager: LogManager | None = field(default=None, compare=False, hash=False)

    @classmethod
    def create(
        cls,
        base_dir: Path | str = "logs",
        started_at: datetime | None = None,
        run_id: str | None = None,
    ) -> RunContext:
        """Create a new RunContext with an isolated log directory and LogManager."""
        if started_at is None:
            started_at = datetime.now()
        if run_id is None:
            run_id = generate_run_id(started_at)
        log_dir = Path(base_dir) / run_id
        log_manager = LogManager(log_dir=log_dir, run_id=run_id)
        return cls(
            run_id=run_id,
            started_at=started_at,
            log_dir=log_dir,
            log_manager=log_manager,
        )


__all__ = [
    "PREVENT_LEGACY_ARCHITECTURE",
    "RunContext",
    "assert_new_architecture",
    "generate_run_id",
]

"""Core runtime utilities for Factor analysis runs.

Canonical location. Manages run IDs, log directories, and execution context.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from core.logging import LogManager


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
    ) -> "RunContext":
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


__all__ = ["generate_run_id", "RunContext"]

"""RunContext representing a single analysis execution context."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from core.runtime.log_manager import LogManager
from core.runtime.run_id import generate_run_id


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
        """Create a new RunContext with an isolated log directory and LogManager.

        Args:
            base_dir: Root directory for runs (defaults to 'logs').
            started_at: Start timestamp (defaults to datetime.now()).
            run_id: Optional custom run_id. If omitted, generates run-YYYYMMDD-HHMMSS-random6.

        Returns:
            A new immutable RunContext instance.
        """
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

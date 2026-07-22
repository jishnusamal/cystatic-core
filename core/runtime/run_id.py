"""Run ID generation for Factor analysis executions.

Generates unique, timestamped, collision-resistant run identifiers:
run-YYYYMMDD-HHMMSS-random6
"""

from __future__ import annotations

import secrets
from datetime import datetime


def generate_run_id(started_at: datetime | None = None) -> str:
    """Generate a unique, filesystem-safe run identifier.

    Format: run-YYYYMMDD-HHMMSS-<6 hex chars>
    Example: run-20260722-104155-8c9f2a

    Args:
        started_at: Optional datetime for the run start time. Defaults to datetime.now().

    Returns:
        Formatted run ID string.
    """
    if started_at is None:
        started_at = datetime.now()

    timestamp_str = started_at.strftime("%Y%m%d-%H%M%S")
    random_suffix = secrets.token_hex(3)
    return f"run-{timestamp_str}-{random_suffix}"

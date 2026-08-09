"""Analysis request and trigger models.

Absorbed from runtime/models/analysis.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from .core import RepositoryReference, PullRequestReference, DiffSnapshot


class AnalysisTrigger(str, Enum):
    """Type of analysis trigger."""

    PULL_REQUEST = "pull_request"
    PUSH = "push"
    MANUAL = "manual"
    SCHEDULED = "scheduled"


@dataclass(frozen=True)
class AnalysisRequest:
    """The pipeline accepts exactly one object.

    Every integration converts its own events into this object.
    """

    repository: RepositoryReference
    pull_request: PullRequestReference | None = None
    diff: DiffSnapshot | None = None
    trigger: AnalysisTrigger = AnalysisTrigger.MANUAL
    metadata: dict[str, Any] | None = None

    @property
    def has_diff(self) -> bool:
        """Check if diff is provided."""
        return self.diff is not None and len(self.diff.files) > 0

    @property
    def is_pull_request(self) -> bool:
        """Check if this is a pull request analysis."""
        return self.pull_request is not None

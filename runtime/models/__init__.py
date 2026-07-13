"""Runtime models for the integration layer.

These models are platform-agnostic and used across all integrations.
"""

from .repository import RepositoryReference, RepositorySnapshot
from .pull_request import PullRequestReference
from .diff import DiffSnapshot, DiffHunk, DiffFile
from .analysis import AnalysisRequest, AnalysisTrigger

__all__ = [
    "AnalysisRequest",
    "AnalysisTrigger",
    "DiffFile",
    "DiffHunk",
    "DiffSnapshot",
    "PullRequestReference",
    "RepositoryReference",
    "RepositorySnapshot",
]
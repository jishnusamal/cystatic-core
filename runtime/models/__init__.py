"""Backward-compatibility shim. Import from models instead."""

from models.core import (
    RepositoryReference,
    RepositorySnapshot,
    PullRequestReference,
    DiffFile,
    DiffHunk,
    DiffSnapshot,
)
from models.analysis import AnalysisRequest, AnalysisTrigger

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

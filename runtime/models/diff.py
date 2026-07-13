"""Diff snapshot models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class DiffHunk:
    """Represents a single hunk in a diff.
    
    Attributes:
        file_path: Path to the file
        source_start: Starting line number in source
        source_length: Number of lines in source
        target_start: Starting line number in target
        target_length: Number of lines in target
        added_lines: List of added line numbers
        removed_lines: List of removed line numbers
        lines: List of diff lines
    """
    
    file_path: str
    source_start: int
    source_length: int
    target_start: int
    target_length: int
    added_lines: tuple[int, ...] = field(default_factory=tuple)
    removed_lines: tuple[int, ...] = field(default_factory=tuple)
    lines: tuple[dict[str, Any], ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DiffFile:
    """Represents a file in a diff.
    
    Attributes:
        file_path: Path to the file
        added_lines: List of added line numbers
        removed_lines: List of removed line numbers
        hunks: List of diff hunks
    """
    
    file_path: str
    added_lines: tuple[int, ...] = field(default_factory=tuple)
    removed_lines: tuple[int, ...] = field(default_factory=tuple)
    hunks: tuple[DiffHunk, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DiffSnapshot:
    """Represents a complete diff snapshot.
    
    Attributes:
        files: List of changed files
        patches: Raw patch data (optional)
        base_sha: Base commit SHA
        head_sha: Head commit SHA
    """
    
    files: tuple[DiffFile, ...] = field(default_factory=tuple)
    patches: tuple[str, ...] = field(default_factory=tuple)
    base_sha: str = ""
    head_sha: str = ""
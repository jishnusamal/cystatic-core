"""Common diff helpers for language adapters."""

from __future__ import annotations

from typing import Dict, List, Optional, Set, Tuple

from schemas.ir import DiffIR, FileDiff, DiffHunk, DiffLine


class DiffUtils:
    """Utility methods for working with diff data."""

    @staticmethod
    def get_changed_lines(file_diff: FileDiff) -> Set[int]:
        """Get all changed target (new-file) line numbers."""
        lines: Set[int] = set()

        for hunk in file_diff.hunks:
            for line in hunk.lines:
                if line.line_type == "added" and line.target_line_no and line.target_line_no > 0:
                    lines.add(line.target_line_no)
                elif line.line_type == "removed" and line.source_line_no and line.source_line_no > 0:
                    lines.add(line.source_line_no)

        return lines

    @staticmethod
    def get_added_lines(file_diff: FileDiff) -> Set[int]:
        """Get all added (new-file) line numbers."""
        lines: Set[int] = set()

        for hunk in file_diff.hunks:
            for line in hunk.lines:
                if line.line_type == "added" and line.target_line_no and line.target_line_no > 0:
                    lines.add(line.target_line_no)

        return lines

    @staticmethod
    def get_removed_lines(file_diff: FileDiff) -> Set[int]:
        """Get all removed (old-file) line numbers."""
        lines: Set[int] = set()

        for hunk in file_diff.hunks:
            for line in hunk.lines:
                if line.line_type == "removed" and line.source_line_no and line.source_line_no > 0:
                    lines.add(line.source_line_no)

        return lines

    @staticmethod
    def get_modification_types(file_diff: FileDiff) -> Dict[str, List[int]]:
        """Classify changed lines by modification type."""
        return {
            "added": sorted(DiffUtils.get_added_lines(file_diff)),
            "removed": sorted(DiffUtils.get_removed_lines(file_diff)),
            "context": sorted(
                DiffUtils.get_changed_lines(file_diff)
                - DiffUtils.get_added_lines(file_diff)
                - DiffUtils.get_removed_lines(file_diff)
            ),
        }

    @staticmethod
    def is_python_file(file_path: str) -> bool:
        """Check if a file is a Python file."""
        return file_path.endswith(".py")

    @staticmethod
    def get_python_files(diff: DiffIR) -> List[FileDiff]:
        """Get only the Python file diffs from a DiffIR."""
        return [
            f for f in diff.files
            if f.file_path and DiffUtils.is_python_file(f.file_path)
        ]
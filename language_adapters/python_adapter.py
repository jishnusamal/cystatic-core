"""Python language analysis adapter."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class PythonAnalysisResult:
    """Summary of static analysis for Python sources."""

    file_paths: list[str] = field(default_factory=list)
    import_edges: list[tuple[str, str]] = field(default_factory=list)


class PythonAdapter:
    """Analyzes Python code for symbols and imports (implementation stub)."""

    def analyze(self, root: Path) -> PythonAnalysisResult:
        """Walk ``root`` and build a minimal analysis result."""
        if not root.is_dir():
            raise FileNotFoundError(root)
        paths = [str(p.relative_to(root)) for p in root.rglob("*.py")]
        return PythonAnalysisResult(file_paths=sorted(paths))

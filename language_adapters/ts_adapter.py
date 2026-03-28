"""TypeScript / JavaScript language analysis adapter."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class TypeScriptAnalysisResult:
    """Summary of static analysis for TS/JS sources."""

    file_paths: list[str] = field(default_factory=list)
    import_edges: list[tuple[str, str]] = field(default_factory=list)


class TypeScriptAdapter:
    """Analyzes TypeScript/JavaScript (implementation stub)."""

    _suffixes = (".ts", ".tsx", ".js", ".jsx")

    def analyze(self, root: Path) -> TypeScriptAnalysisResult:
        """Walk ``root`` and collect TS/JS files."""
        if not root.is_dir():
            raise FileNotFoundError(root)
        paths: list[str] = []
        for p in root.rglob("*"):
            if p.is_file() and p.suffix in self._suffixes:
                paths.append(str(p.relative_to(root)))
        return TypeScriptAnalysisResult(file_paths=sorted(paths))

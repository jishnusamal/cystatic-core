from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RepositoryMaterializationMetrics:
    """Request-scoped repository materialization metrics."""

    repository_files: int = 0
    repository_bytes: int = 0

    _materialized_paths: set[str] = field(default_factory=set)
    materialized_bytes: int = 0

    repository_acquisition_ms: float = 0.0
    repository_indexing_ms: float = 0.0

    facts_generated: int = 0
    blob_cache_hits: int = 0
    blob_cache_misses: int = 0
    indexed_files: int = 0

    def set_repository_size(
        self,
        *,
        files: int,
        bytes: int,
    ) -> None:
        self.repository_files = files
        self.repository_bytes = bytes

    def record_file(
        self,
        *,
        path: str,
        size: int = 0,
    ) -> None:
        # Materialization is counted by unique repository path.
        if path in self._materialized_paths:
            return

        self._materialized_paths.add(path)
        self.materialized_bytes += size

    @property
    def materialized_files(self) -> int:
        return len(self._materialized_paths)

    @property
    def materialization_ratio(self) -> float:
        if self.repository_files == 0:
            return 0.0

        return self.materialized_files / self.repository_files

    @property
    def materialization_percent(self) -> float:
        return self.materialization_ratio * 100

    @property
    def materialization_bytes_ratio(self) -> float:
        if self.repository_bytes == 0:
            return 0.0

        return self.materialized_bytes / self.repository_bytes

    @property
    def materialization_bytes_percent(self) -> float:
        return self.materialization_bytes_ratio * 100

    def snapshot(self) -> dict[str, int | float]:
        return {
            "repository_acquisition_ms": round(self.repository_acquisition_ms, 3),
            "repository_indexing_ms": round(self.repository_indexing_ms, 3),
            "repository_files": self.repository_files,
            "materialized_files": self.materialized_files,
            "materialization_ratio": round(self.materialization_ratio, 6),
            "materialization_percent": round(self.materialization_percent, 4),
            "repository_bytes": self.repository_bytes,
            "materialized_bytes": self.materialized_bytes,
            "materialization_bytes_ratio": round(self.materialization_bytes_ratio, 6),
            "materialization_bytes_percent": round(
                self.materialization_bytes_percent, 4
            ),
            "facts_generated": self.facts_generated,
            "blob_cache_hits": self.blob_cache_hits,
            "blob_cache_misses": self.blob_cache_misses,
            "indexed_files": self.indexed_files,
        }

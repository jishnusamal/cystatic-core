from __future__ import annotations

import fnmatch
from pydantic import BaseModel, Field  # pyright: ignore[reportMissingImports]


class FileExclusionConfig(BaseModel):
    excluded_globs: list[str] = Field(
        default_factory=lambda: [
            # "**/migrations/**",
            "**/alembic/versions/**",
            "**/__pycache__/**",
            "**/generated/**",
            "**/*.generated.py",
            "**/*_pb2.py",
            "**/*_pb2_grpc.py",
        ]
    )


class FileExclusionService:
    def __init__(self, config: FileExclusionConfig | None = None):
        self.config = config or FileExclusionConfig()

    def is_excluded(self, file_path: str) -> bool:
        return self.get_exclusion_match(file_path) is not None

    def get_exclusion_match(self, file_path: str) -> str | None:
        normalized = file_path.lstrip("./")
        for pattern in self.config.excluded_globs:
            if fnmatch.fnmatch(normalized, pattern):
                return pattern
        return None

    def filter_files(self, files: list[dict]) -> list[dict]:
        return [
            file
            for file in files
            if not self.is_excluded(str(file.get("file_path", "")))
        ]

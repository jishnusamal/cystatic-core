from dataclasses import dataclass

from .ids import FileId


@dataclass(frozen=True, slots=True)
class File:
    """Represents a source file in the repository."""

    id: FileId
    path: str
    language: str

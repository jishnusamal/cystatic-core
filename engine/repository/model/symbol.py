"""Symbol model - represents a discovered symbol in the repository."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import sys

from .evidence import Evidence, FileLocation


class SymbolKind(str, Enum):
    """Type of symbol."""

    FUNCTION = "function"
    METHOD = "method"
    CLASS = "class"
    INTERFACE = "interface"
    ENUM = "enum"
    CONSTANT = "constant"
    VARIABLE = "variable"
    IMPORT = "import"
    MODULE = "module"
    PACKAGE = "package"


class SymbolVisibility(str, Enum):
    """Symbol visibility/access modifier."""

    PUBLIC = "public"
    PRIVATE = "private"
    PROTECTED = "protected"
    INTERNAL = "internal"
    PACKAGE = "package"


@dataclass(slots=True, frozen=True)
class Symbol:
    """
    Represents a discovered symbol in the repository.

    A symbol is any named entity in the source code: functions, classes,
    methods, variables, imports, etc.

    Attributes:
        id: Stable identifier (e.g., "python://module.py::function_name")
        name: Human-readable name
        kind: Type of symbol
        language: Programming language
        file: Source file path
        range: (start_line, end_line) tuple
        visibility: Access visibility
        evidence: Provenance evidence for this symbol
        properties: Additional language-specific metadata
    """

    id: str
    name: str
    kind: SymbolKind
    language: str
    file: str
    range: tuple[int, int]
    visibility: SymbolVisibility = SymbolVisibility.PUBLIC
    evidence: Evidence | None = None
    properties: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Validate symbol after initialization."""
        if not self.id:
            raise ValueError("Symbol id cannot be empty")
        if not self.name:
            raise ValueError("Symbol name cannot be empty")
        if not self.file:
            raise ValueError("Symbol file cannot be empty")
        if not isinstance(self.range, tuple) or len(self.range) != 2:
            raise ValueError(f"Symbol range must be a 2-tuple: {self.range}")
        if self.range[0] < 0 or self.range[1] < 0:
            raise ValueError(f"Symbol range cannot have negative values: {self.range}")
        if self.range[0] > self.range[1]:
            raise ValueError(f"Symbol range start cannot exceed end: {self.range}")

        # Intern high-cardinality string fields
        object.__setattr__(self, "id", sys.intern(self.id))
        object.__setattr__(self, "name", sys.intern(self.name))
        object.__setattr__(self, "file", sys.intern(self.file))
        object.__setattr__(self, "language", sys.intern(self.language))

        if isinstance(self.properties, dict):
            object.__setattr__(self, "properties", dict(self.properties))
        if self.evidence is None:
            # Auto-generate evidence from file and range
            object.__setattr__(
                self,
                "evidence",
                Evidence(
                    file_location=FileLocation(
                        file=self.file,
                        start_line=self.range[0] + 1,  # Convert 0-based to 1-based
                        end_line=self.range[1] + 1,
                    )
                ),
            )

    def __hash__(self):
        """Hash based on stable identifier only."""
        return hash(self.id)

    def __eq__(self, other):
        """Equality based on stable identifier only."""
        if not isinstance(other, Symbol):
            return NotImplemented
        return self.id == other.id

    @property
    def start_line(self) -> int:
        """Get the start line of this symbol."""
        return self.range[0]

    @property
    def end_line(self) -> int:
        """Get the end line of this symbol."""
        return self.range[1]

    @property
    def line_count(self) -> int:
        """Get the number of lines this symbol spans."""
        return self.end_line - self.start_line + 1

"""
ChangedSymbol — represents every symbol modified by a change.

Responsibilities:
  - symbol extraction
  - ownership
  - file metadata
  - language metadata
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from .enums import SymbolKind


class ChangedSymbol(BaseModel):
    """A symbol that was modified by a change.

    Attributes:
        symbol: The bare symbol name.
        qualified_name: Fully qualified name (e.g. ``module.ClassName.method``).
        kind: Classification of the symbol (function, method, class, etc.).
        language: Programming language of the source file.
        file_path: Path to the source file.
        module: Module or package the symbol belongs to.
        owner: Team or individual responsible for this symbol.
        service: Microservice or bounded context containing this symbol.
        domain: Business domain this symbol belongs to.
        extraction_confidence: Confidence in the extraction (0.0–1.0).
    """
    symbol: str = Field(..., min_length=1)
    qualified_name: str | None = None
    kind: SymbolKind

    language: str = Field(..., min_length=1)

    file_path: str = Field(..., min_length=1)
    module: str | None = None

    owner: str | None = None
    service: str | None = None
    domain: str | None = None

    extraction_confidence: float = Field(default=1.0, ge=0.0, le=1.0)
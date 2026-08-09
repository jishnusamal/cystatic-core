"""Evidence model - provenance for every deterministic fact in the compiler.

Every compiled fact must be traceable back to repository evidence.
Evidence provides the chain of provenance from source code to model.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class FileLocation:
    """
    A precise location in a source file.

    Attributes:
        file: Source file path
        start_line: Start line number (1-based)
        end_line: End line number (1-based, inclusive)
        start_column: Start column number (1-based, optional)
        end_column: End column number (1-based, optional)
    """
    file: str
    start_line: int
    end_line: int
    start_column: int = 0
    end_column: int = 0

    def __post_init__(self):
        """Validate file location after initialization."""
        if not self.file:
            raise ValueError("File path cannot be empty")
        if self.start_line < 1:
            raise ValueError(f"Start line must be >= 1: {self.start_line}")
        if self.end_line < self.start_line:
            raise ValueError(
                f"End line ({self.end_line}) must be >= start line ({self.start_line})"
            )


@dataclass(frozen=True)
class SymbolReference:
    """
    A reference to a symbol in the repository.

    Attributes:
        symbol_id: The stable identifier of the referenced symbol
        location: File location where the reference occurs
    """
    symbol_id: str
    location: FileLocation

    def __post_init__(self):
        """Validate symbol reference after initialization."""
        if not self.symbol_id:
            raise ValueError("Symbol id cannot be empty")


@dataclass(frozen=True)
class CallReference:
    """
    Evidence for a function/method call.

    Attributes:
        caller_symbol_id: Symbol id of the caller
        callee_name: Name of the called function/method
        location: File location where the call occurs
        call_type: Type of call (direct, indirect, dynamic)
    """
    caller_symbol_id: str
    callee_name: str
    location: FileLocation
    call_type: str = "direct"

    def __post_init__(self):
        """Validate call reference after initialization."""
        if not self.caller_symbol_id:
            raise ValueError("Caller symbol id cannot be empty")
        if not self.callee_name:
            raise ValueError("Callee name cannot be empty")


@dataclass(frozen=True)
class ImportReference:
    """
    Evidence for an import statement.

    Attributes:
        module: The imported module name
        names: Imported names (for from-imports)
        location: File location where the import occurs
        import_type: Type of import (import, from_import, etc.)
    """
    module: str
    names: tuple[str, ...]
    location: FileLocation
    import_type: str = "import"

    def __post_init__(self):
        """Validate import reference after initialization."""
        if not self.module:
            raise ValueError("Module cannot be empty")
        if isinstance(self.names, list):
            object.__setattr__(self, 'names', tuple(self.names))


@dataclass(frozen=True)
class AnnotationReference:
    """
    Evidence for an annotation/decorator.

    Attributes:
        annotation_name: Name of the annotation/decorator
        location: File location where the annotation occurs
        arguments: Annotation arguments if available
    """
    annotation_name: str
    location: FileLocation
    arguments: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Validate annotation reference after initialization."""
        if not self.annotation_name:
            raise ValueError("Annotation name cannot be empty")
        if isinstance(self.arguments, dict):
            object.__setattr__(self, 'arguments', dict(self.arguments))


@dataclass(frozen=True)
class Evidence:
    """
    Provenance evidence for a compiled fact.

    Every deterministic fact in the compiler carries evidence that traces
    it back to the original source code. Evidence is the chain of custody
    for all compiled information.

    Attributes:
        file_location: Primary file location for this evidence
        symbol_references: References to related symbols
        call_references: References to related function calls
        import_references: References to related imports
        annotation_references: References to related annotations
        source: Raw source text or description of the evidence
    """
    file_location: FileLocation
    symbol_references: tuple[SymbolReference, ...] = field(default_factory=tuple)
    call_references: tuple[CallReference, ...] = field(default_factory=tuple)
    import_references: tuple[ImportReference, ...] = field(default_factory=tuple)
    annotation_references: tuple[AnnotationReference, ...] = field(default_factory=tuple)
    source: str = ""

    def __post_init__(self):
        """Validate evidence after initialization."""
        if isinstance(self.symbol_references, list):
            object.__setattr__(self, 'symbol_references', tuple(self.symbol_references))
        if isinstance(self.call_references, list):
            object.__setattr__(self, 'call_references', tuple(self.call_references))
        if isinstance(self.import_references, list):
            object.__setattr__(self, 'import_references', tuple(self.import_references))
        if isinstance(self.annotation_references, list):
            object.__setattr__(self, 'annotation_references', tuple(self.annotation_references))

    @staticmethod
    def from_file(file: str, start_line: int, end_line: int) -> 'Evidence':
        """
        Create evidence from a simple file location.

        Args:
            file: Source file path
            start_line: Start line number
            end_line: End line number

        Returns:
            Evidence with just a file location
        """
        return Evidence(
            file_location=FileLocation(
                file=file,
                start_line=start_line,
                end_line=end_line,
            )
        )

    @staticmethod
    def from_symbol(
        file: str,
        start_line: int,
        end_line: int,
        symbol_id: str,
    ) -> 'Evidence':
        """
        Create evidence from a symbol reference.

        Args:
            file: Source file path
            start_line: Start line number
            end_line: End line number
            symbol_id: The referenced symbol's id

        Returns:
            Evidence with file location and symbol reference
        """
        return Evidence(
            file_location=FileLocation(
                file=file,
                start_line=start_line,
                end_line=end_line,
            ),
            symbol_references=(
                SymbolReference(
                    symbol_id=symbol_id,
                    location=FileLocation(
                        file=file,
                        start_line=start_line,
                        end_line=end_line,
                    ),
                ),
            ),
        )
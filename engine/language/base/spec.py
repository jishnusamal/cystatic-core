"""Language specification metadata."""

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class LanguageSpec:
    """Immutable, hashable, and lightweight language specification metadata."""

    id: str
    extensions: frozenset[str]
    filenames: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        """Validate invariants for LanguageSpec."""
        if not self.id:
            raise ValueError("LanguageSpec.id must not be empty")
        if not isinstance(self.extensions, frozenset):
            raise TypeError("LanguageSpec.extensions must be a frozenset")
        if not isinstance(self.filenames, frozenset):
            raise TypeError("LanguageSpec.filenames must be a frozenset")

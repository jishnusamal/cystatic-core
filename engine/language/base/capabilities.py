"""Language capabilities metadata."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LanguageCapabilities:
    """Immutable, hashable, and lightweight language capabilities metadata.

    Capabilities describe what analysis a language adapter supports,
    allowing downstream pipeline stages to execute or skip analysis
    gracefully without hardcoding language IDs.

    Attributes:
        symbols: Adapter can reliably extract declarations/symbols.
        imports: Adapter can extract imports/dependencies.
        calls: Adapter can extract call relationships.
        types: Adapter can provide useful type information.
        entrypoints: Adapter can identify language-specific application entrypoints.
        events: Adapter can extract event publication/subscription information.
        persistence: Adapter can identify persistence/database-related structures.
        tests: Adapter can identify test structures/frameworks.
    """

    symbols: bool = True
    imports: bool = True
    calls: bool = True
    types: bool = False
    entrypoints: bool = False
    events: bool = False
    persistence: bool = False
    tests: bool = False

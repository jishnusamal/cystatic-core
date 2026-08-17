from dataclasses import dataclass, field
from typing import Set
from .requirements import ResolutionRequirement
from engine.repository.query import SymbolId

@dataclass
class ResolutionFrontier:
    """Manages the set‑based frontier for lazy resolution.

    Attributes:
        symbols: Symbols currently participating in impact traversal.
        paths: Repository paths discovered as candidates for resolving the frontier.
        unresolved: Symbols whose required facts are not currently complete.
    """
    symbols: Set[SymbolId] = field(default_factory=set)
    paths: Set[str] = field(default_factory=set)
    unresolved: Set[ResolutionRequirement] = field(default_factory=set)

    def add_symbol(self, symbol: SymbolId) -> None:
        self.symbols.add(symbol)

    def add_path(self, path: str) -> None:
        self.paths.add(path)

    def add_unresolved(self, req: ResolutionRequirement) -> None:
        self.unresolved.add(req)

    def has_work(self) -> bool:
        return bool(self.symbols) or bool(self.unresolved)

    def clear(self) -> None:
        self.symbols.clear()
        self.paths.clear()
        self.unresolved.clear()

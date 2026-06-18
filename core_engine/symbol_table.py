"""
Layer 1 — Symbol Canonicalization

Replaces full symbol names with short deterministic IDs (T1, T2, T3...).
Sorted by change_influence.score descending.
Max 30 symbols.
"""
from __future__ import annotations

from typing import Any


class SymbolTable:
    """Canonical symbol ID mapping for LLM payload compression."""

    def __init__(self, max_symbols: int = 30):
        self.symbol_to_id: dict[str, str] = {}
        self.id_to_symbol: dict[str, str] = {}
        self.metadata: dict[str, dict[str, Any]] = {}
        self._max_symbols = max_symbols
        self._counter = 0

    def build(self, change_influence: list[dict[str, Any]]) -> "SymbolTable":
        """Build symbol table from change_influence entries.

        Args:
            change_influence: List of dicts with 'symbol', 'domain', 'influence_score', 'risk_tags'.

        Returns:
            Self for chaining.
        """
        # Sort by influence_score descending
        sorted_entries = sorted(
            change_influence,
            key=lambda x: x.get("influence_score", 0.0),
            reverse=True,
        )

        # Cap to max_symbols
        capped = sorted_entries[: self._max_symbols]

        for entry in capped:
            symbol = entry.get("symbol", "")
            if not symbol:
                continue

            # Assign deterministic ID
            self._counter += 1
            sid = f"T{self._counter}"

            self.symbol_to_id[symbol] = sid
            self.id_to_symbol[sid] = symbol
            self.metadata[sid] = {
                "domain": entry.get("domain", "general"),
                "score": round(entry.get("influence_score", 0.0), 3),
            }

        return self

    def to_dict(self) -> dict[str, Any]:
        """Output format for LLM."""
        return {
            "symbols": self.metadata,
        }

    def get_id(self, symbol: str) -> str | None:
        """Get canonical ID for a symbol, or None if not in table."""
        return self.symbol_to_id.get(symbol)

    def get_symbol(self, sid: str) -> str | None:
        """Get original symbol from ID, or None if not found."""
        return self.id_to_symbol.get(sid)

    def map_symbols(self, symbols: list[str]) -> list[str]:
        """Convert a list of symbol names to their canonical IDs.
        Unknown symbols are passed through unchanged."""
        result = []
        for sym in symbols:
            cid = self.symbol_to_id.get(sym)
            result.append(cid if cid else sym)
        return result

    def __len__(self) -> int:
        return len(self.symbol_to_id)
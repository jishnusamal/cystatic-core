"""
Layer 1 — Change Influence Compressor

Compresses change_influence list into compact format for LLM payload.
Keeps only symbol ID, influence score, and risk tags.
Drops file paths, raw change graphs, diff metadata.
"""
from __future__ import annotations

from typing import Any


def compress_change_influence(
    change_influence: list[dict[str, Any]] | None,
    symbol_table: Any | None = None,
    max_symbols: int = 30,
) -> list[dict[str, Any]]:
    """Compress change_influence for LLM payload.

    Args:
        change_influence: List of change influence dicts.
        symbol_table: SymbolTable instance for ID mapping (optional).
        max_symbols: Maximum number of symbols to include.

    Returns:
        List of compressed change influence dicts.
    """
    if not change_influence:
        return []

    compressed = []
    for entry in change_influence[:max_symbols]:
        symbol = entry.get("symbol", "")
        if not symbol:
            continue

        # Map to canonical ID if symbol_table provided
        if symbol_table:
            sid = symbol_table.get_id(symbol) or symbol
        else:
            sid = symbol

        compressed.append({
            "id": sid,
            "score": round(entry.get("influence_score", 0.0), 3),
            "tags": entry.get("risk_tags", []),
        })

    return compressed
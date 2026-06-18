"""
Layer 2 — Soft Edge Compressor

Compresses soft propagation edges into compact format for LLM payload.
Drops metadata objects, keeps only essential fields.
"""
from __future__ import annotations

from typing import Any


def compress_soft_edges(
    soft_edges: list[dict[str, Any]] | None,
    symbol_table: Any | None = None,
    min_confidence: float = 0.25,
    max_edges: int = 25,
) -> list[list[Any]]:
    """Compress soft propagation edges for LLM payload.

    Args:
        soft_edges: List of soft edge dicts from soft_propagation module.
        symbol_table: SymbolTable instance for ID mapping (optional).
        min_confidence: Minimum confidence threshold (drop edges below this).
        max_edges: Maximum number of edges to include.

    Returns:
        List of compressed edge lists: [from_id, to_id, confidence, type]
    """
    if not soft_edges:
        return []

    compressed = []
    for edge in soft_edges:
        # Skip edges below confidence threshold
        confidence = edge.get("confidence", 0.0)
        if confidence < min_confidence:
            continue

        # Get from/to symbols
        from_sym = edge.get("from", "") or edge.get("from_symbol", "")
        to_sym = edge.get("to", "") or edge.get("to_symbol", "")

        if not from_sym or not to_sym:
            continue

        # Map to canonical IDs if symbol_table provided
        if symbol_table:
            from_sym = symbol_table.get_id(from_sym) or from_sym
            to_sym = symbol_table.get_id(to_sym) or to_sym

        # Get edge type (enum only)
        edge_type = edge.get("source", edge.get("edge_type", "semantic_propagation"))

        compressed.append([
            from_sym,
            to_sym,
            round(confidence, 3),
            edge_type,
        ])

    # Sort by confidence descending (keep highest confidence edges)
    compressed.sort(key=lambda x: x[2], reverse=True)

    # Cap to max_edges
    return compressed[:max_edges]
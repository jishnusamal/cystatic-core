"""
Layer 2 — Execution Path Compressor

Compresses execution paths into compact causal primitives for LLM payload.
Replaces symbols with canonical IDs, drops file names and code references.
"""
from __future__ import annotations

from typing import Any


def compress_paths(
    execution_paths: dict[str, Any] | None,
    symbol_table: Any | None = None,
    max_paths: int = 5,
    max_nodes: int = 8,
) -> list[dict[str, Any]]:
    """Compress execution paths for LLM payload.

    Args:
        execution_paths: Raw execution paths dict from execution_paths module.
        symbol_table: SymbolTable instance for ID mapping (optional).
        max_paths: Maximum number of paths to include.
        max_nodes: Maximum nodes per path.

    Returns:
        List of compressed path dicts.
    """
    if not execution_paths:
        return []

    raw_paths = execution_paths.get("paths", [])
    if not raw_paths:
        return []

    compressed = []
    for path in raw_paths[:max_paths]:
        nodes = path.get("nodes", [])
        if not nodes:
            continue

        # Map symbols to IDs if symbol_table provided
        if symbol_table:
            nodes = symbol_table.map_symbols(nodes)

        # Cap nodes
        nodes = nodes[:max_nodes]

        # Extract risk hop types from key_risk_points
        risk_points = path.get("key_risk_points", [])
        risk_hops = []
        for rp in risk_points:
            if isinstance(rp, dict):
                risk_hops.append(rp.get("risk_type", ""))
            elif isinstance(rp, str):
                risk_hops.append(rp)

        # Deduplicate risk hops
        risk_hops = list(dict.fromkeys(risk_hops))

        compressed.append({
            "id": f"P{len(compressed) + 1}",
            "nodes": nodes,
            "risk_hops": risk_hops,
            "confidence": round(path.get("path_confidence", 0.0), 3),
        })

    return compressed
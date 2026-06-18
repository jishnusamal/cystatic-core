"""
Layer 4 — LLM Packet Builder (Final Compression)

Builds the final token-bounded LLM payload from compressed causal primitives.
Enforces 8,000 token hard limit with pruning strategy.
"""
from __future__ import annotations

import json
from typing import Any

from core_engine.symbol_table import SymbolTable
from core_engine.path_compressor import compress_paths
from core_engine.soft_edge_compressor import compress_soft_edges
from core_engine.change_influence_compressor import compress_change_influence
from core_engine.constraint_compressor import compress_constraints


def estimate_tokens(obj: Any) -> int:
    """Estimate token count from JSON serialization.

    Uses rough heuristic: 1 token ≈ 4 characters.
    """
    return len(json.dumps(obj)) // 4


def prune_lowest_confidence_items(packet: dict[str, Any]) -> None:
    """Prune lowest-confidence items to reduce token count.

    Priority order (drop in this order):
    1. Soft edges (lowest confidence first)
    2. Low-risk zones
    3. Execution paths (lowest confidence first)
    4. Cap symbol count (30 → 20 → 15 fallback)

    Modifies packet in place.
    """
    # 1. Drop soft edges first (up to 50%)
    if "soft_edges" in packet and packet["soft_edges"]:
        current = len(packet["soft_edges"])
        target = max(current // 2, 0)
        # Already sorted by confidence desc, so drop from end
        packet["soft_edges"] = packet["soft_edges"][:target]

    # 2. Drop low-risk zones (keep only high-impact domains)
    if "risk_zones" in packet and packet["risk_zones"]:
        high_impact_domains = {
            "checkout", "invoice", "payment", "billing", "order",
            "tax", "money_movement", "fulfillment",
        }
        filtered = [z for z in packet["risk_zones"] if z in high_impact_domains]
        if filtered:
            packet["risk_zones"] = filtered

    # 3. Drop execution paths (lowest confidence first)
    if "execution_paths" in packet and packet["execution_paths"]:
        current = len(packet["execution_paths"])
        target = max(current // 2, 1)
        # Sort by confidence desc, keep top half
        paths = sorted(
            packet["execution_paths"],
            key=lambda x: x.get("confidence", 0.0),
            reverse=True,
        )
        packet["execution_paths"] = paths[:target]

    # 4. Cap symbol count (30 → 20 → 15 fallback)
    if "symbols" in packet and packet["symbols"]:
        current_symbols = len(packet["symbols"])
        if current_symbols > 15:
            # Keep top 15 by score
            sorted_syms = sorted(
                packet["symbols"].items(),
                key=lambda x: x[1].get("score", 0.0),
                reverse=True,
            )
            packet["symbols"] = dict(sorted_syms[:15])


def build_llm_packet(
    change_influence: list[dict[str, Any]] | None,
    execution_paths: dict[str, Any] | None,
    soft_edges: list[dict[str, Any]] | None,
    constraints: dict[str, Any] | None,
    risk_zones: list[str] | None,
    changed_symbols: list[str] | None,
    repo: str = "",
    pr_number: int = 0,
    token_budget: int = 7500,
    impact_propagation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build final LLM packet with token safety guard.

    Args:
        change_influence: Raw change influence list.
        execution_paths: Raw execution paths dict.
        soft_edges: Raw soft edges list.
        constraints: Raw constraints dict.
        risk_zones: List of risk zone strings.
        changed_symbols: List of changed symbol names.
        repo: Repository name.
        pr_number: PR number.
        token_budget: Maximum token count (default 7500, hard limit 8000).
        impact_propagation: Impact Propagation Kernel result dict (optional).

    Returns:
        Final LLM packet dict, guaranteed to be within token budget.
    """
    # Layer 1: Build symbol table
    symbol_table = SymbolTable(max_symbols=30)
    symbol_table.build(change_influence or [])

    # Layer 1: Compress change_influence
    compressed_influence = compress_change_influence(
        change_influence,
        symbol_table=symbol_table,
        max_symbols=30,
    )

    # Layer 2: Compress execution paths
    compressed_paths = compress_paths(
        execution_paths,
        symbol_table=symbol_table,
        max_paths=5,
        max_nodes=8,
    )

    # Layer 2: Compress soft edges
    compressed_edges = compress_soft_edges(
        soft_edges,
        symbol_table=symbol_table,
        min_confidence=0.25,
        max_edges=25,
    )

    # Layer 4: Compress constraints
    compressed_constraints = compress_constraints(constraints)

    # Build initial packet (keys match LLM.generate() signature)
    packet = {
        "repo": repo,
        "pr_number": pr_number,
        "change_influence": compressed_influence,
        "execution_paths": compressed_paths,
        "soft_edges": compressed_edges,
        "constraints": compressed_constraints,
        "risk_zones": risk_zones or ["general"],
        "changed_symbols": changed_symbols or [],
    }

    # Include Impact Propagation Kernel output as additional context
    # (compact dict with risk_summary, failure_simulation, blast_radius)
    if impact_propagation:
        packet["impact_propagation"] = impact_propagation

    # Token safety guard
    token_estimate = estimate_tokens(packet)
    if token_estimate > token_budget:
        # Prune iteratively until within budget
        for _ in range(10):  # Max 10 pruning iterations
            if estimate_tokens(packet) <= token_budget:
                break
            prune_lowest_confidence_items(packet)

    # Final hard check
    if estimate_tokens(packet) > 8000:
        # Emergency: strip to absolute minimum
        packet = {
            "repo": repo,
            "pr_number": pr_number,
            "change_influence": [],
            "execution_paths": [],
            "soft_edges": [],
            "constraints": compressed_constraints,
            "risk_zones": (risk_zones or ["general"])[:3],
            "changed_symbols": (changed_symbols or [])[:10],
        }
        if impact_propagation:
            # Keep impact_propagation in emergency mode too
            # — it's already compact structured data
            packet["impact_propagation"] = impact_propagation

    return packet

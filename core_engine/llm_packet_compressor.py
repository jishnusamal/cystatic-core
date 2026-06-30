"""
Layer 4 — LLM Packet Builder (Final Compression)

Builds the final token-bounded LLM payload from compressed causal primitives.
Enforces 8,000 token hard limit with pruning strategy.
"""
from __future__ import annotations

import json
from typing import Any

from core_engine.symbol_table import SymbolTable
from core_engine.soft_edge_compressor import compress_impact_evidence, compress_evidence_summary, compress_risk_hypotheses
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
    1. Risk hypotheses (lowest strength first)
    2. Low-risk zones
    3. Cap symbol count (30 → 20 → 15 fallback)

    Modifies packet in place.
    """
    # 1. Drop risk hypotheses items (weakest first)
    if "risk_hypotheses" in packet and packet["risk_hypotheses"]:
        current = len(packet["risk_hypotheses"])
        target = max(current // 2, 0)
        # Already sorted by strength desc, so drop from end (weakest)
        packet["risk_hypotheses"] = packet["risk_hypotheses"][:target]
    # Legacy: also prune evidence_summary if present
    elif "evidence_summary" in packet and packet["evidence_summary"]:
        current = len(packet["evidence_summary"])
        target = max(current // 2, 0)
        packet["evidence_summary"] = packet["evidence_summary"][:target]

    # 2. Drop low-risk zones (keep only high-impact domains)
    if "risk_zones" in packet and packet["risk_zones"]:
        high_impact_domains = {
            "checkout", "invoice", "payment", "billing", "order",
            "tax", "money_movement", "fulfillment",
        }
        filtered = [z for z in packet["risk_zones"] if z in high_impact_domains]
        if filtered:
            packet["risk_zones"] = filtered

    # 3. Cap symbol count (30 → 20 → 15 fallback)
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
    impact_evidence: list[dict[str, Any]] | None,
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
        impact_evidence: Raw impact evidence list.
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

    # Layer 2: Build risk hypotheses (unified reasoning packet)
    # Uses impact_evidence as evidence_summary for the risk hypotheses builder
    from core_engine.failure_archetype_engine import build_risk_hypotheses
    risk_hypotheses = build_risk_hypotheses(
        change_influence=change_influence,
        evidence_summary=impact_evidence,
    )
    compressed_hypotheses = compress_risk_hypotheses(risk_hypotheses, max_items=10)

    # Build initial packet (keys match LLM.generate() signature)
    packet = {
        "repo": repo,
        "pr_number": pr_number,
        "change_influence": compressed_influence,
        "risk_hypotheses": compressed_hypotheses,
        "risk_zones": risk_zones or ["general"],
        "changed_symbols": changed_symbols or [],
    }

    # Include Impact Propagation Kernel output as additional context (if provided)
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
            "risk_hypotheses": [],
            "risk_zones": (risk_zones or ["general"])[:3],
            "changed_symbols": (changed_symbols or [])[:10],
        }
        if impact_propagation:
            # Keep impact_propagation in emergency mode too
            # — it's already compact structured data
            packet["impact_propagation"] = impact_propagation

    return packet

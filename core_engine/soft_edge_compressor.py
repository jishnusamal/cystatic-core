"""
Layer 2 — Impact Evidence Compressor

Compresses impact evidence / evidence summaries into compact format for LLM payload.
Now also supports risk_hypotheses compression.

The deterministic engine now sends "what appears involved?" as pre-synthesized
risk hypotheses, so the LLM writes reasons rather than infers connections.
"""
from __future__ import annotations

from typing import Any


def compress_evidence_summary(
    evidence_summary: list[dict[str, Any]] | None,
    max_items: int = 10,
) -> list[dict[str, Any]]:
    """Compress evidence summary for LLM payload.

    Args:
        evidence_summary: List of EvidenceSummary dicts from impact_evidence.synthesize_evidence_summary().
        max_items: Maximum number of summary items to include.

    Returns:
        List of compressed evidence summary dicts.
    """
    if not evidence_summary:
        return []

    # Sort by confidence descending, take top items
    sorted_items = sorted(
        evidence_summary,
        key=lambda x: x.get("confidence", 0.0),
        reverse=True,
    )

    compressed = []
    for item in sorted_items[:max_items]:
        compressed.append({
            "risk_area": item.get("risk_area", "unknown"),
            "confidence": round(item.get("confidence", 0.0), 3),
            "evidence_strength": item.get("evidence_strength", "WEAK"),
            "evidence": item.get("evidence", [])[:3],           # max 3 claims
            "supporting_symbols": item.get("supporting_symbols", [])[:8],  # max 8 symbols
        })

    return compressed


def compress_risk_hypotheses(
    risk_hypotheses: list[dict[str, Any]] | None,
    max_items: int = 10,
) -> list[dict[str, Any]]:
    """Compress risk hypotheses for LLM payload.

    Risk hypotheses are the unified replacement for both evidence_summary
    and failure_archetypes. Each hypothesis is:
      {
        "area": "tax_to_invoice",
        "strength": "WEAK",
        "symbols": [...],
        "possible_failures": [...]
      }

    Args:
        risk_hypotheses: List of risk hypothesis dicts from build_risk_hypotheses().
        max_items: Maximum number of hypotheses to include.

    Returns:
        List of compressed risk hypothesis dicts.
    """
    if not risk_hypotheses:
        return []

    # Already sorted by strength desc, take top items
    compressed = []
    for item in risk_hypotheses[:max_items]:
        compressed.append({
            "area": item.get("area", "unknown"),
            "strength": item.get("strength", "WEAK"),
            "symbols": item.get("symbols", [])[:8],                      # max 8 symbols
            "possible_failures": item.get("possible_failures", [])[:6],   # max 6 failure archetypes
        })

    return compressed


def compress_impact_evidence(
    impact_evidence: list[dict[str, Any]] | None,
    symbol_table: Any | None = None,
    min_confidence: float = 0.25,
    max_evidence: int = 25,
) -> list[list[Any]]:
    """Compress impact evidence for LLM payload (legacy format, kept for backward compat).

    Prefer compress_risk_hypotheses() for new pipeline — it produces richer,
    pre-synthesized clusters that the LLM doesn't need to reason about.

    Args:
        impact_evidence: List of impact evidence dicts from impact_evidence module.
        symbol_table: SymbolTable instance for ID mapping (optional).
        min_confidence: Minimum confidence threshold (drop below this).
        max_evidence: Maximum number of evidence items to include.

    Returns:
        List of compressed evidence lists: [source_id, target_id, confidence, type]
    """
    if not impact_evidence:
        return []

    compressed = []
    for ev in impact_evidence:
        # Skip evidence below confidence threshold
        confidence = ev.get("confidence", 0.0)
        if confidence < min_confidence:
            continue

        # Get source/target symbols
        source_sym = ev.get("source_symbol", "") or ev.get("from", "") or ev.get("from_symbol", "")
        target_sym = ev.get("target_symbol", "") or ev.get("to", "") or ev.get("to_symbol", "")

        if not source_sym or not target_sym:
            continue

        # Map to canonical IDs if symbol_table provided
        if symbol_table:
            source_sym = symbol_table.get_id(source_sym) or source_sym
            target_sym = symbol_table.get_id(target_sym) or target_sym

        # Get evidence type
        evidence_type = ev.get("evidence_type", ev.get("source", ev.get("edge_type", "canonical_flow")))

        compressed.append([
            source_sym,
            target_sym,
            round(confidence, 3),
            evidence_type,
        ])

    # Sort by confidence descending (keep highest confidence evidence)
    compressed.sort(key=lambda x: x[2], reverse=True)

    # Cap to max_evidence
    return compressed[:max_evidence]
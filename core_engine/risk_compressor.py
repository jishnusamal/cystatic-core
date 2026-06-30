"""
Risk Compressor — transforms atomic risk areas into broader risk families.

Pipeline:
  1. Map atomic risks to broader families (RISK_FAMILIES)
  2. Aggregate evidence (symbols) by family, deduplicate
  3. Aggregate failure modes by family
  4. Calculate family strength (use strongest child)
  5. Apply business impact scoring with weights
  6. Keep only top N families
  7. Produce LLM-friendly output with token compression
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any


# ═══════════════════════════════════════════════════════════════════════════
# Step 1: Risk Families
# ═══════════════════════════════════════════════════════════════════════════

RISK_FAMILIES: dict[str, dict[str, Any]] = {
    "financial_integrity": {
        "members": [
            "money_flow_related",
            "numeric_precision_related",
            "data_freshness_related",
        ]
    },
    "execution_safety": {
        "members": [
            "retry_sensitive_related",
            "transaction_boundary_related",
            "irreversible_related",
        ]
    },
    "state_consistency": {
        "members": [
            "state_mutation_related",
        ]
    },
    "dependency_risk": {
        "members": [
            "external_dependency_related",
        ]
    },
}

# Reverse mapping: atomic area → family
_AREA_TO_FAMILY: dict[str, str] = {}
for family, config in RISK_FAMILIES.items():
    for member in config["members"]:
        _AREA_TO_FAMILY[member] = family


# ═══════════════════════════════════════════════════════════════════════════
# Step 5: Business Impact Scoring
# ═══════════════════════════════════════════════════════════════════════════

RISK_WEIGHTS: dict[str, int] = {
    "financial_integrity": 100,
    "execution_safety": 90,
    "dependency_risk": 70,
    "state_consistency": 50,
}

_STRENGTH_BONUS: dict[str, int] = {
    "STRONG": 50,
    "MEDIUM": 25,
    "WEAK": 0,
}

_STRENGTH_ORDER = {"STRONG": 0, "MEDIUM": 1, "WEAK": 2}


# ═══════════════════════════════════════════════════════════════════════════
# Step 2 & 3: Aggregate Evidence and Failure Modes
# ═══════════════════════════════════════════════════════════════════════════

def _get_family_for_area(area: str) -> str | None:
    """Map an atomic risk area to its family, or None if unmapped."""
    return _AREA_TO_FAMILY.get(area)


def _aggregate_by_family(
    risk_hypotheses: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Aggregate risk hypotheses by family.

    Returns:
        Dict of family_name → {
            "why_flagged": list of atomic areas,
            "symbols": deduplicated list of symbols,
            "possible_failures": deduplicated list of failures,
            "strengths": list of strength labels from children,
        }
    """
    families: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "why_flagged": [],
        "symbols": [],
        "possible_failures": [],
        "strengths": [],
        "symbol_set": set(),
        "failure_set": set(),
    })

    for hypothesis in risk_hypotheses:
        area = hypothesis.get("area", "")
        family = _get_family_for_area(area)
        if family is None:
            continue

        entry = families[family]

        # Track which atomic areas triggered this family
        if area not in entry["why_flagged"]:
            entry["why_flagged"].append(area)

        # Deduplicate symbols
        for sym in hypothesis.get("symbols", []):
            if sym and sym not in entry["symbol_set"]:
                entry["symbol_set"].add(sym)
                entry["symbols"].append(sym)

        # Deduplicate failure modes
        for failure in hypothesis.get("possible_failures", []):
            if failure and failure not in entry["failure_set"]:
                entry["failure_set"].add(failure)
                entry["possible_failures"].append(failure)

        # Collect strength for Step 4
        strength = hypothesis.get("strength", "WEAK")
        if strength:
            entry["strengths"].append(strength)

    return dict(families)


# ═══════════════════════════════════════════════════════════════════════════
# Step 4: Calculate Family Strength
# ═══════════════════════════════════════════════════════════════════════════

def _compute_family_strength(strengths: list[str]) -> str:
    """Use strongest child strength.

    if any(child == "STRONG"): strength = "STRONG"
    elif any(child == "MEDIUM"): strength = "MEDIUM"
    else: strength = "LOW"
    """
    if not strengths:
        return "WEAK"
    if "STRONG" in strengths:
        return "STRONG"
    if "MEDIUM" in strengths:
        return "MEDIUM"
    return "WEAK"


# ═══════════════════════════════════════════════════════════════════════════
# Step 5: Calculate Family Score
# ═══════════════════════════════════════════════════════════════════════════

def _compute_family_score(
    family: str,
    strength: str,
    symbol_count: int,
    failure_count: int,
) -> int:
    """Compute final score for a family.

    score = family_weight + symbol_count + failure_count + strength_bonus
    """
    weight = RISK_WEIGHTS.get(family, 0)
    bonus = _STRENGTH_BONUS.get(strength, 0)
    return weight + symbol_count + failure_count + bonus


# ═══════════════════════════════════════════════════════════════════════════
# Step 6: Keep Only Top N
# ═══════════════════════════════════════════════════════════════════════════

def _select_top_families(
    compressed_risks: list[dict[str, Any]],
    top_n: int = 3,
) -> list[dict[str, Any]]:
    """Sort by score descending and keep top N."""
    sorted_risks = sorted(
        compressed_risks,
        key=lambda r: r["score"],
        reverse=True,
    )
    return sorted_risks[:top_n]


# ═══════════════════════════════════════════════════════════════════════════
# Step 7 & 8: LLM-Friendly Output with Token Compression
# ═══════════════════════════════════════════════════════════════════════════

def _compress_for_llm(
    family: str,
    strength: str,
    symbols: list[str],
    possible_failures: list[str],
    why_flagged: list[str],
    score: int = 0,
    max_symbols: int = 3,
    max_failures: int = 3,
) -> dict[str, Any]:
    """Produce LLM-friendly output with token compression.

    Matches Step 8 format from task spec:
    - family, strength, why_flagged (evidence)
    - symbol_count, representative_symbols (compressed symbols, NO full list)
    - possible_failures (compressed)
    - score (for ranking context)
    """
    return {
        "family": family,
        "strength": strength,
        "score": score,
        "why_flagged": why_flagged,
        "symbol_count": len(symbols),
        "representative_symbols": symbols[:max_symbols],
        "possible_failures": possible_failures[:max_failures],
    }


# ═══════════════════════════════════════════════════════════════════════════
# Main Pipeline
# ═══════════════════════════════════════════════════════════════════════════

def compress_risk_hypotheses(
    risk_hypotheses: list[dict[str, Any]],
    top_n: int = 3,
    compress_for_llm: bool = True,
) -> list[dict[str, Any]]:
    """Compress atomic risk hypotheses into broader risk families.

    Args:
        risk_hypotheses: List of risk hypothesis dicts (from failure_archetype_engine).
            Each should have: area, strength, symbols, possible_failures
        top_n: Number of top families to keep (default 3).
        compress_for_llm: If True, produce token-compressed output for LLM consumption.

    Returns:
        List of compressed risk dicts, sorted by score descending.
        Each dict has:
            - family: str
            - strength: str
            - score: int
            - why_flagged: list[str]
            - symbol_count: int
            - representative_symbols: list[str] (capped at 3)
            - possible_failures: list[str] (capped at 3)
    """
    # Step 2 & 3: Aggregate by family
    aggregated = _aggregate_by_family(risk_hypotheses)

    # Build intermediate results
    compressed: list[dict[str, Any]] = []
    for family, data in aggregated.items():
        strength = _compute_family_strength(data["strengths"])
        symbol_count = len(data["symbols"])
        failure_count = len(data["possible_failures"])
        score = _compute_family_score(family, strength, symbol_count, failure_count)

        entry: dict[str, Any] = {
            "family": family,
            "strength": strength,
            "score": score,
            "why_flagged": data["why_flagged"],
            "symbols": data["symbols"],
            "possible_failures": data["possible_failures"],
        }

        if compress_for_llm:
            # Compressed output: only representative fields, NO full lists
            entry = {
                "family": family,
                "strength": strength,
                "score": score,
                "why_flagged": data["why_flagged"],
                "symbol_count": len(data["symbols"]),
                "representative_symbols": data["symbols"][:3],
                "possible_failures": data["possible_failures"][:3],
            }
        else:
            # Full output: include complete lists
            entry = {
                "family": family,
                "strength": strength,
                "score": score,
                "why_flagged": data["why_flagged"],
                "symbols": data["symbols"],
                "possible_failures": data["possible_failures"],
            }

        compressed.append(entry)

    # Step 6: Keep only top N families
    top_families = _select_top_families(compressed, top_n=top_n)

    return top_families


# ═══════════════════════════════════════════════════════════════════════════
# Convenience: full pipeline from enriched files
# ═══════════════════════════════════════════════════════════════════════════

def compress_risks_from_enriched_files(
    enriched_files: list[dict[str, Any]],
    top_n: int = 3,
    compress_for_llm: bool = True,
) -> list[dict[str, Any]]:
    """Full pipeline: enriched files → risk hypotheses → compressed families.

    This is a convenience function that chains:
      1. build_risk_hypotheses (from failure_archetype_engine)
      2. compress_risk_hypotheses (this module)

    Args:
        enriched_files: Enriched file data from orchestrator.
        top_n: Number of top families to keep.
        compress_for_llm: If True, produce token-compressed output.

    Returns:
        List of compressed risk family dicts.
    """
    # Import here to avoid circular dependency
    from core_engine.failure_archetype_engine import build_risk_hypotheses

    # Build risk hypotheses from enriched files
    # We need to extract change_influence and evidence_summary from enriched_files
    change_influence: list[dict[str, Any]] = []
    evidence_summary: list[dict[str, Any]] = []

    for file_data in enriched_files:
        # Extract risk tags from keyword_signals
        risk_tags: list[str] = []
        for signal in file_data.get("keyword_signals", []) or []:
            keyword = signal.keyword if hasattr(signal, "keyword") else str(signal)
            risk_tags.append(keyword.lower())

        # Extract changed functions as change_influence entries
        for fn in file_data.get("changed_functions", []) or []:
            fn_data = fn if isinstance(fn, dict) else {}
            symbol = fn_data.get("name", "")
            if not symbol:
                continue

            change_influence.append({
                "symbol": symbol,
                "domain": fn_data.get("domain", "general"),
                "risk_tags": risk_tags,
                "influence_score": fn_data.get("influence_score", 0.0),
            })

        # Build evidence_summary entries from risk areas detected
        # Group by risk_area patterns
        area_symbols: dict[str, list[str]] = defaultdict(list)
        for entry in change_influence:
            for tag in entry.get("risk_tags", []):
                area = f"{tag}_related"
                area_symbols[area].append(entry["symbol"])

        for area, symbols in area_symbols.items():
            evidence_summary.append({
                "risk_area": area,
                "confidence": 0.5,
                "supporting_symbols": list(set(symbols)),
                "evidence_strength": "WEAK",
            })

    # Build risk hypotheses
    risk_hypotheses = build_risk_hypotheses(
        change_influence=change_influence,
        evidence_summary=evidence_summary,
    )

    # Compress to families
    compressed = compress_risk_hypotheses(
        risk_hypotheses=risk_hypotheses,
        top_n=top_n,
        compress_for_llm=compress_for_llm,
    )

    return compressed
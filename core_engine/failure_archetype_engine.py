"""
Failure Archetype Engine — Risk Hypotheses Generator.

Produces structured risk_hypotheses that replace BOTH evidence_summary
and failure_archetypes with a single, information-dense reasoning packet.

Each risk_hypothesis is:
  {
    "area": "tax_to_invoice",
    "strength": "WEAK",
    "symbols": ["_update_checkout_tax", "_tax_item_label", "tax_rate_from_breakdown"],
    "possible_failures": ["tax_calculation_error", "invoice_drift", "amount_mismatch"]
  }

This is nearly the perfect reasoning packet for the LLM:
  - Observed propagation area
  + Evidence strength
  + Relevant symbols
  + Failure archetypes
  = Enough context to generate believable merge-risk narratives.

Pipeline:
  1. Aggregate Risk Signals from change_influence entries
  2. Build area hypotheses from evidence summary (risk_area → hypothesis)
  3. Expand hypotheses with possible_failures from tag → archetype mappings
  4. Attach symbols and strength
  5. Score and deduplicate

Input:
  change_influence: list[dict] — each has symbol, domain, risk_tags, influence_score
  evidence_summary: list[dict] — each has risk_area, confidence, supporting_symbols

Output:
  risk_hypotheses: list[dict] — each has area, strength, symbols, possible_failures
"""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any


# ═══════════════════════════════════════════════════════════════════════════
# Risk tags → failure archetypes they can trigger
# ═══════════════════════════════════════════════════════════════════════════

TAG_TO_ARCHETYPES: dict[str, list[str]] = {
    "money_flow": [
        "amount_mismatch",
        "invoice_drift",
        "settlement_discrepancy",
    ],
    "retry_sensitive": [
        "duplicate_execution",
        "duplicate_charge",
    ],
    "state_mutation": [
        "invalid_state_transition",
        "stale_state_propagation",
    ],
    "transaction_boundary": [
        "partial_commit",
        "consistency_failure",
    ],
    "external_dependency": [
        "unexpected_response_shape",
        "downstream_logic_failure",
    ],
    "numeric_precision": [
        "rounding_error",
        "tax_calculation_error",
    ],
    "data_freshness": [
        "stale_read",
        "reconciliation_mismatch",
    ],
    "irreversible": [
        "unrecoverable_side_effect",
    ],
    "security": [
        "auth_bypass",
        "permission_escalation",
    ],
    "auth_boundary": [
        "auth_bypass",
        "session_hijack",
    ],
    "session_dependency": [
        "session_hijack",
        "stale_state_propagation",
    ],
    "async_boundary": [
        "duplicate_execution",
        "consistency_failure",
    ],
    "side_effect": [
        "unrecoverable_side_effect",
        "downstream_logic_failure",
    ],
    "race_condition": [
        "stale_state_propagation",
        "consistency_failure",
    ],
    "time_sensitive": [
        "subscription_cycle_error",
        "stale_read",
    ],
}

ALL_ARCHETYPES: set[str] = {
    arch for archetypes in TAG_TO_ARCHETYPES.values() for arch in archetypes
}

# ═══════════════════════════════════════════════════════════════════════════
# Tag Weights
# ═══════════════════════════════════════════════════════════════════════════

TAG_WEIGHTS: dict[str, float] = {
    "money_flow": 1.0,
    "transaction_boundary": 1.0,
    "irreversible": 1.0,
    "retry_sensitive": 0.8,
    "external_dependency": 0.7,
    "state_mutation": 0.6,
    "security": 0.6,
    "auth_boundary": 0.6,
    "numeric_precision": 0.5,
    "data_freshness": 0.5,
    "session_dependency": 0.4,
    "async_boundary": 0.4,
    "side_effect": 0.4,
    "race_condition": 0.3,
    "time_sensitive": 0.3,
}

DEFAULT_TAG_WEIGHT: float = 0.3

# ═══════════════════════════════════════════════════════════════════════════
# Evidence Boost Map — risk_area patterns → failure archetypes they boost
# ═══════════════════════════════════════════════════════════════════════════

_EVIDENCE_BOOST_MAP: dict[str, list[tuple[str, float]]] = {
    "tax_to_invoice": [
        ("invoice_drift", 0.3),
        ("amount_mismatch", 0.3),
        ("tax_calculation_error", 0.25),
    ],
    "invoice_to_payment": [
        ("invoice_drift", 0.2),
        ("amount_mismatch", 0.2),
        ("settlement_discrepancy", 0.25),
    ],
    "order_to_payment": [
        ("duplicate_charge", 0.3),
        ("partial_commit", 0.2),
    ],
    "order_to_invoice": [
        ("invoice_drift", 0.2),
        ("amount_mismatch", 0.2),
    ],
    "checkout_to_order": [
        ("duplicate_execution", 0.2),
        ("invalid_state_transition", 0.2),
    ],
    "checkout_to_payment": [
        ("duplicate_charge", 0.25),
        ("partial_commit", 0.2),
    ],
    "payment_to_ledger": [
        ("settlement_discrepancy", 0.3),
        ("consistency_failure", 0.2),
    ],
    "auth_to_session": [
        ("auth_bypass", 0.2),
        ("session_hijack", 0.2),
    ],
    "user_to_auth": [
        ("auth_bypass", 0.15),
        ("permission_escalation", 0.15),
    ],
    "payment_to_notification": [
        ("unrecoverable_side_effect", 0.15),
        ("downstream_logic_failure", 0.15),
    ],
    "fulfillment_to_notification": [
        ("downstream_logic_failure", 0.15),
    ],
    "cart_to_checkout": [
        ("invalid_state_transition", 0.15),
        ("stale_state_propagation", 0.15),
    ],
    "billing_to_payment": [
        ("amount_mismatch", 0.15),
        ("settlement_discrepancy", 0.15),
    ],
    "subscription_to_billing": [
        ("subscription_cycle_error", 0.25),
        ("invoice_drift", 0.15),
    ],
    "discount_to_cart": [
        ("rounding_error", 0.15),
        ("amount_mismatch", 0.15),
    ],
    "inventory_to_fulfillment": [
        ("stale_read", 0.15),
        ("consistency_failure", 0.15),
    ],
}

# Generic risk area patterns (catch-alls if no domain pair matches)
_GENERIC_EVIDENCE_BOOST: dict[str, list[tuple[str, float]]] = {
    "payment": [("duplicate_charge", 0.2), ("partial_commit", 0.15)],
    "tax": [("tax_calculation_error", 0.2), ("invoice_drift", 0.15)],
    "invoice": [("invoice_drift", 0.2), ("amount_mismatch", 0.15)],
    "order": [("duplicate_execution", 0.15), ("invalid_state_transition", 0.15)],
    "checkout": [("duplicate_execution", 0.15), ("invalid_state_transition", 0.15)],
    "billing": [("amount_mismatch", 0.15), ("invoice_drift", 0.15)],
    "auth": [("auth_bypass", 0.15), ("permission_escalation", 0.1)],
}


# ═══════════════════════════════════════════════════════════════════════════
# Strength label helper
# ═══════════════════════════════════════════════════════════════════════════

def _strength_label(score: float) -> str:
    """Map a numeric score to a strength label."""
    if score >= 0.6:
        return "STRONG"
    elif score >= 0.35:
        return "MEDIUM"
    return "WEAK"


def _compute_strength_from_signals(
    change_influence: list[dict[str, Any]],
    area: str,
) -> str:
    """Compute evidence strength for an area based on risk tag signals."""
    score = 0.0
    parts = area.split("_")
    for entry in change_influence:
        for tag in entry.get("risk_tags", []):
            weight = TAG_WEIGHTS.get(tag, DEFAULT_TAG_WEIGHT)
            # Boost if any part of the area matches tag relevance
            for part in parts:
                if part in tag or tag in part:
                    score += weight * 0.25
                    break
    capped = min(score, 1.0)
    return _strength_label(capped)


def _collect_possible_failures_for_area(
    area: str,
    weighted_tags: dict[str, float] | None = None,
) -> list[str]:
    """Collect possible failure archetypes relevant to a given area.

    Sources:
    1. Evidence boost map (area → archetypes)
    2. Generic keyword matches
    3. Tag-derived archetypes if weighted_tags provided
    """
    failures: set[str] = set()

    # 1. Direct evidence boost map match
    boosts = _EVIDENCE_BOOST_MAP.get(area, [])
    for archetype, _boost in boosts:
        failures.add(archetype)

    # 2. Generic keyword fallback
    if not boosts:
        for keyword, generic_boosts in _GENERIC_EVIDENCE_BOOST.items():
            if keyword in area.lower():
                for archetype, _boost in generic_boosts:
                    failures.add(archetype)
                break

    # 3. Tag-derived archetypes
    if weighted_tags:
        area_parts = set(area.lower().split("_"))
        for tag, _weighted_score in weighted_tags.items():
            # If tag relates to this area, add its archetypes
            for part in area_parts:
                if part in tag or tag in part:
                    for arch in TAG_TO_ARCHETYPES.get(tag, []):
                        failures.add(arch)
                    break

    # If nothing found, try matching any tag that contains area parts
    if not failures and weighted_tags:
        area_parts = set(area.lower().split("_"))
        for tag in weighted_tags:
            if tag in area_parts or any(p in tag for p in area_parts):
                for arch in TAG_TO_ARCHETYPES.get(tag, []):
                    failures.add(arch)

    return sorted(failures)


# ═══════════════════════════════════════════════════════════════════════════
# Main builder
# ═══════════════════════════════════════════════════════════════════════════

def build_risk_hypotheses(
    change_influence: list[dict[str, Any]] | None = None,
    evidence_summary: list[dict[str, Any]] | None = None,
    min_strength: str = "WEAK",
) -> list[dict[str, Any]]:
    """Build risk_hypotheses from change_influence and evidence_summary.

    Replaces BOTH evidence_summary and failure_archetypes with a single
    information-dense reasoning packet.

    Each hypothesis is:
      {
        "area": "tax_to_invoice",
        "strength": "WEAK",
        "symbols": ["_update_checkout_tax", "_tax_item_label", "tax_rate_from_breakdown"],
        "possible_failures": ["tax_calculation_error", "invoice_drift", "amount_mismatch"]
      }

    Args:
        change_influence: List of ChangeInfluence dicts.
            Each entry should have 'symbol', 'domain', 'risk_tags', 'influence_score'.
        evidence_summary: List of EvidenceSummary dicts (from synthesize_evidence_summary).
            Each entry should have 'risk_area', 'confidence', 'supporting_symbols', 'evidence_strength'.
        min_strength: Minimum strength to include ("WEAK", "MEDIUM", "STRONG").

    Returns:
        List of risk_hypothesis dicts, sorted by strength descending.
    """
    change_influence = change_influence or []
    evidence_summary = evidence_summary or []

    # Aggregate weighted tags from change_influence
    weighted_tags = _aggregate_risk_signals(change_influence)

    # Build hypotheses from evidence_summary areas
    hypotheses: list[dict[str, Any]] = []
    seen_areas: set[str] = set()

    # Priority 1: evidence_summary areas (these are the primary signal)
    for ev in evidence_summary:
        area = ev.get("risk_area", "")
        if not area or area in seen_areas:
            continue
        seen_areas.add(area)

        # Determine strength (use evidence_strength if available, else compute)
        strength = ev.get("evidence_strength", "WEAK")
        if strength == "WEAK":
            # Upgrade based on confidence
            confidence = ev.get("confidence", 0.0)
            if confidence >= 0.5:
                strength = _strength_label(confidence)

        # Collect symbols
        symbols = list(ev.get("supporting_symbols", []))

        # Collect possible failures
        possible_failures = _collect_possible_failures_for_area(area, weighted_tags)

        # If no failures found, try tag-based deduction
        if not possible_failures:
            for tag in weighted_tags:
                for arch in TAG_TO_ARCHETYPES.get(tag, []):
                    possible_failures.append(arch)
            possible_failures = sorted(set(possible_failures))

        hypotheses.append({
            "area": area,
            "strength": strength,
            "symbols": symbols,
            "possible_failures": possible_failures,
        })

    # Priority 2: tag-derived hypotheses (areas not covered by evidence_summary)
    if weighted_tags:
        tag_hypotheses = _build_tag_derived_hypotheses(
            weighted_tags=weighted_tags,
            change_influence=change_influence,
            seen_areas=seen_areas,
        )
        hypotheses.extend(tag_hypotheses)

    # Sort by strength descending (STRONG > MEDIUM > WEAK)
    strength_order = {"STRONG": 0, "MEDIUM": 1, "WEAK": 2}
    hypotheses.sort(key=lambda h: (strength_order.get(h["strength"], 3), h["area"]))

    # Filter by minimum strength
    min_order = strength_order.get(min_strength, 2)
    hypotheses = [
        h for h in hypotheses
        if strength_order.get(h["strength"], 3) <= min_order
    ]

    return hypotheses


# ═══════════════════════════════════════════════════════════════════════════
# Aggregation helpers
# ═══════════════════════════════════════════════════════════════════════════

def _aggregate_risk_signals(
    change_influence: list[dict[str, Any]],
) -> dict[str, float]:
    """Aggregate risk tags to produce weighted frequency scores.

    For each risk tag:
      1. Count how many changed symbols carry this tag.
      2. Multiply by tag weight.
      3. Sum across all symbols.

    Returns dict of tag → weighted_score.
    """
    tag_counts: Counter[str] = Counter()

    for entry in change_influence:
        for tag in entry.get("risk_tags", []):
            tag_counts[tag] += 1

    weighted: dict[str, float] = {}
    for tag, count in tag_counts.items():
        weight = TAG_WEIGHTS.get(tag, DEFAULT_TAG_WEIGHT)
        weighted[tag] = count * weight

    return weighted


def _build_tag_derived_hypotheses(
    weighted_tags: dict[str, float],
    change_influence: list[dict[str, Any]],
    seen_areas: set[str],
) -> list[dict[str, Any]]:
    """Build risk hypotheses from risk tags for areas not already covered."""
    hypotheses: list[dict[str, Any]] = []

    # Determine areas implied by tags
    for tag, _score in weighted_tags.items():
        # Use the tag itself as an area hint
        area_area = f"{tag}_related"
        if area_area in seen_areas:
            continue

        # Collect symbols with this tag
        symbols: list[str] = []
        for entry in change_influence:
            if tag in entry.get("risk_tags", []):
                sym = entry.get("symbol", "")
                if sym and sym not in symbols:
                    symbols.append(sym)

        # Collect possible failures from this tag
        possible_failures = TAG_TO_ARCHETYPES.get(tag, [])
        if not possible_failures:
            continue

        # Compute strength from tag weight
        tag_weight = TAG_WEIGHTS.get(tag, DEFAULT_TAG_WEIGHT)
        strength = _strength_label(tag_weight)

        seen_areas.add(area_area)
        hypotheses.append({
            "area": area_area,
            "strength": strength,
            "symbols": symbols[:5],  # cap at 5 symbols
            "possible_failures": possible_failures,
        })

    return hypotheses
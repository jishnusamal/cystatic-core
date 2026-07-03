"""
llm_input_builder — the only interface between the deterministic engine and the LLM.

This module converts deterministic engine internals into reviewer-ready facts.
The LLM never sees evidence clusters, hypotheses, scenarios, causal graphs,
or any other internal implementation detail.

Design rule:
    If this JSON were displayed directly in the Factor UI without an LLM,
    would it still make sense to an experienced engineer?

    If yes, you've found the right abstraction level.
"""
from __future__ import annotations

from typing import Any

from core_engine.models.evidence_bundle import EvidenceBundle
from core_engine.models.change_understanding import ChangeUnderstanding


def build_llm_input(
    bundle: EvidenceBundle,
    understanding: ChangeUnderstanding,
    repo: str = "",
    pr_number: int = 0,
) -> dict[str, Any]:
    """Build the LLM input from deterministic engine outputs.

    This is the ONLY function that constructs data for the LLM.
    The LLM receives reviewer-ready facts — not internal implementation artifacts.

    Args:
        bundle: EvidenceBundle from EvidencePipeline.
        understanding: ChangeUnderstanding from ChangeUnderstandingPipeline.
        repo: Repository name.
        pr_number: PR number.

    Returns:
        A dict containing only reviewer-ready facts, following the llm_input schema.
    """
    # ── Repository context ──────────────────────────────────────────────
    llm_input: dict[str, Any] = {
        "repository": {
            "name": repo,
            "language": _detect_language(bundle),
            "framework": _detect_framework(bundle),
        },
        "pull_request": {
            "number": pr_number,
            "title": "",
            "description": "",
            "analysis_mode": "FULL_FILE",
        },
    }

    # ── Change summary ──────────────────────────────────────────────────
    changed_domains = list(bundle.domains) if bundle.domains else []
    changed_business_objects = [
        bo.name for bo in bundle.business_objects if bo.name
    ]
    changed_symbols_list = [cs.symbol for cs in bundle.changed_symbols]

    llm_input["change_summary"] = {
        "changed_domains": changed_domains,
        "changed_business_objects": changed_business_objects,
        "high_risk_symbols": _extract_high_risk_symbols(bundle),
        "files_changed": len(understanding.enriched_files) if understanding.enriched_files else 0,
        "symbols_changed": len(changed_symbols_list),
    }

    # ── Review findings ─────────────────────────────────────────────────
    review_findings = _build_review_findings(bundle, understanding)
    llm_input["review_findings"] = review_findings

    # ── Existing validation ─────────────────────────────────────────────
    llm_input["existing_validation"] = {
        "covered_domains": _extract_covered_domains(bundle),
        "missing_tests": _extract_missing_tests(bundle, understanding),
        "known_assumptions": _extract_known_assumptions(bundle),
    }

    # ── Deterministic verdict ───────────────────────────────────────────
    llm_input["deterministic_verdict"] = {
        "status": _compute_deterministic_verdict(bundle),
        "confidence": round(bundle.confidence, 2),
    }

    return llm_input


# ═══════════════════════════════════════════════════════════════════════════
# Internal builders
# ═══════════════════════════════════════════════════════════════════════════


def _extract_high_risk_symbols(bundle: EvidenceBundle) -> list[str]:
    """Extract symbols that carry elevated risk.

    These are symbols that appear in risk anchors, cross-domain evidence,
    or transaction boundaries.
    """
    high_risk: set[str] = set()

    # Symbols from risk anchors
    for ra in bundle.risk_anchors:
        if ra.symbol:
            high_risk.add(ra.symbol)

    # Symbols involved in cross-domain evidence
    for ev in bundle.impact_evidence:
        if ev.evidence_type and "cross" in ev.evidence_type.lower():
            high_risk.add(ev.source.name)
            high_risk.add(ev.target.name)

    # Symbols from transaction boundary constraints
    for c in bundle.constraints:
        if c.symbol and c.constraint_type and "transaction" in c.constraint_type.lower():
            high_risk.add(c.symbol)

    return list(high_risk)


def _build_review_findings(
    bundle: EvidenceBundle,
    understanding: ChangeUnderstanding,
) -> list[dict[str, Any]]:
    """Build review findings from deterministic evidence.

    Each finding represents a reviewer-ready observation about
    an architectural concern, not an internal analysis artifact.
    """
    findings: list[dict[str, Any]] = []

    # ── Finding 1: Cross-domain evidence ────────────────────────────────
    cross_domain_evidence = [
        ev for ev in bundle.impact_evidence
        if ev.evidence_type and "cross" in ev.evidence_type.lower()
    ]
    if cross_domain_evidence:
        for ev in cross_domain_evidence[:3]:  # Max 3 cross-domain findings
            finding = _evidence_to_finding(ev, bundle)
            if finding:
                findings.append(finding)

    # ── Finding 2: Risk anchors ─────────────────────────────────────────
    for ra in bundle.risk_anchors[:3]:  # Max 3 risk anchor findings
        finding = _risk_anchor_to_finding(ra, bundle)
        if finding:
            findings.append(finding)

    # ── Finding 3: High-confidence impact evidence ──────────────────────
    high_conf_evidence = [
        ev for ev in bundle.impact_evidence
        if ev.confidence >= 0.8
    ]
    for ev in high_conf_evidence[:3]:  # Max 3 high-confidence findings
        finding = _evidence_to_finding(ev, bundle)
        if finding and not _already_in_findings(finding, findings):
            findings.append(finding)

    # ── Finding 4: Side effects with production impact ──────────────────
    for se in bundle.side_effects[:2]:  # Max 2 side-effect findings
        finding = _side_effect_to_finding(se, bundle)
        if finding:
            findings.append(finding)

    return findings


def _evidence_to_finding(
    ev: Any,
    bundle: EvidenceBundle,
) -> dict[str, Any] | None:
    """Convert a single ImpactEvidence to a review finding."""
    try:
        source_name = ev.source.name if hasattr(ev.source, "name") else str(ev.source)
        target_name = ev.target.name if hasattr(ev.target, "name") else str(ev.target)
        evidence_type = ev.evidence_type.value if hasattr(ev.evidence_type, "value") else str(ev.evidence_type)
    except Exception:
        return None

    # Determine affected domains
    affected_domains = _domains_for_symbols([source_name, target_name], bundle)

    # Determine affected business objects
    affected_bos = _business_objects_for_symbols([source_name, target_name], bundle)

    # Build evidence list
    evidence = [
        f"{source_name} connects to {target_name} via {evidence_type}",
    ]
    if ev.explanation:
        evidence.append(ev.explanation)

    # Build production impact description
    production_impact = _describe_production_impact(
        source_name, target_name, evidence_type, affected_domains, affected_bos,
    )

    # Build recommended validation
    recommended_validation = _recommend_validation(
        source_name, target_name, affected_domains,
    )

    return {
        "id": f"RF-{len(evidence):03d}",
        "severity": _compute_severity(ev.confidence, evidence_type),
        "confidence": round(ev.confidence, 2),
        "title": f"{source_name} → {target_name}",
        "summary": ev.explanation or f"Change in {source_name} may affect {target_name}",
        "affected_domains": affected_domains,
        "business_objects": affected_bos,
        "symbols": [source_name, target_name],
        "evidence": evidence,
        "production_impact": production_impact,
        "recommended_validation": recommended_validation,
        "missing_evidence": _missing_evidence_for(evidence_type),
    }


def _risk_anchor_to_finding(
    ra: Any,
    bundle: EvidenceBundle,
) -> dict[str, Any] | None:
    """Convert a RiskAnchor to a review finding."""
    try:
        symbol = ra.symbol if hasattr(ra, "symbol") else ""
        anchor_type = ra.anchor_type.value if hasattr(ra.anchor_type, "value") else str(getattr(ra, "anchor_type", "generic"))
        description = ra.description if hasattr(ra, "description") else ""
    except Exception:
        return None

    if not symbol:
        return None

    affected_domains = _domains_for_symbols([symbol], bundle)
    affected_bos = _business_objects_for_symbols([symbol], bundle)

    return {
        "id": f"RF-ANCHOR-{symbol[:20]}",
        "severity": "HIGH",
        "confidence": 0.85,
        "title": f"Risk anchor: {symbol} ({anchor_type})",
        "summary": description or f"{symbol} is a {anchor_type} risk anchor",
        "affected_domains": affected_domains,
        "business_objects": affected_bos,
        "symbols": [symbol],
        "evidence": [
            f"{symbol} classified as {anchor_type} risk anchor",
        ],
        "production_impact": f"Changes to {symbol} may affect {', '.join(affected_domains) if affected_domains else 'downstream systems'}",
        "recommended_validation": f"Verify {symbol} behavior in affected domains",
        "missing_evidence": [
            "Runtime call path",
            "Integration coverage",
        ],
    }


def _side_effect_to_finding(
    se: Any,
    bundle: EvidenceBundle,
) -> dict[str, Any] | None:
    """Convert a SideEffect to a review finding."""
    try:
        symbol = se.symbol if hasattr(se, "symbol") else ""
        effect_type = se.effect_type.value if hasattr(se.effect_type, "value") else str(getattr(se, "effect_type", "unknown"))
        description = se.description if hasattr(se, "description") else ""
    except Exception:
        return None

    if not symbol:
        return None

    affected_domains = _domains_for_symbols([symbol], bundle)

    return {
        "id": f"RF-SIDE-{symbol[:20]}",
        "severity": "MEDIUM" if "external" in effect_type.lower() or "http" in effect_type.lower() else "LOW",
        "confidence": 0.75,
        "title": f"Side effect: {symbol} ({effect_type})",
        "summary": description or f"{symbol} introduces {effect_type} side effect",
        "affected_domains": affected_domains,
        "business_objects": _business_objects_for_symbols([symbol], bundle),
        "symbols": [symbol],
        "evidence": [
            f"{symbol} has {effect_type} side effect",
        ],
        "production_impact": f"Side effect in {symbol} may cause unexpected behavior in {', '.join(affected_domains) if affected_domains else 'dependent systems'}",
        "recommended_validation": f"Verify {symbol} side effect handling",
        "missing_evidence": [
            "Error handling coverage",
            "Rollback behavior",
        ],
    }


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════


def _domains_for_symbols(symbols: list[str], bundle: EvidenceBundle) -> list[str]:
    """Find domains associated with given symbols."""
    domains: set[str] = set()
    for ev in bundle.impact_evidence:
        try:
            source_name = ev.source.name if hasattr(ev.source, "name") else str(ev.source)
            target_name = ev.target.name if hasattr(ev.target, "name") else str(ev.target)
            if source_name in symbols or target_name in symbols:
                if ev.evidence_type and "domain" in ev.evidence_type.lower():
                    domains.add(source_name)
                    domains.add(target_name)
        except Exception:
            continue
    # Fall back to bundle domains
    if not domains and bundle.domains:
        domains.update(bundle.domains[:3])
    return list(domains)[:5]


def _business_objects_for_symbols(symbols: list[str], bundle: EvidenceBundle) -> list[str]:
    """Find business objects associated with given symbols."""
    bos: set[str] = set()
    for bo in bundle.business_objects:
        if bo.name:
            bos.add(bo.name)
    return list(bos)[:5]


def _compute_severity(confidence: float, evidence_type: str) -> str:
    """Compute severity from confidence and evidence type."""
    high_risk_types = {
        "money_flow", "transaction", "payment", "billing",
        "cross_domain", "external_dependency", "auth",
    }
    if any(rt in evidence_type.lower() for rt in high_risk_types):
        return "HIGH"
    if confidence >= 0.8:
        return "HIGH"
    if confidence >= 0.6:
        return "MEDIUM"
    return "LOW"


def _describe_production_impact(
    source: str,
    target: str,
    evidence_type: str,
    domains: list[str],
    business_objects: list[str],
) -> str:
    """Describe the production impact of a finding."""
    parts = []
    if business_objects:
        parts.append(f"{', '.join(business_objects[:3])} may be affected")
    if domains:
        parts.append(f"impact reaches {', '.join(domains[:3])}")
    if not parts:
        parts.append(f"{source} changes may propagate to {target}")
    return ". ".join(parts)


def _recommend_validation(source: str, target: str, domains: list[str]) -> str:
    """Recommend validation for a finding."""
    if domains:
        return f"End-to-end {', '.join(domains[:2])} verification"
    return f"{source} → {target} integration test"


def _missing_evidence_for(evidence_type: str) -> list[str]:
    """Suggest missing evidence based on evidence type."""
    suggestions = []
    if "cross" in evidence_type.lower():
        suggestions.append("Runtime call path")
        suggestions.append("Integration coverage")
    if "external" in evidence_type.lower():
        suggestions.append("External system behavior under failure")
    if "transaction" in evidence_type.lower():
        suggestions.append("Transaction rollback behavior")
    if not suggestions:
        suggestions.append("Runtime call path")
    return suggestions


def _already_in_findings(finding: dict, findings: list[dict]) -> bool:
    """Check if a finding is already in the list (by title)."""
    title = finding.get("title", "")
    return any(f.get("title", "") == title for f in findings)


def _extract_covered_domains(bundle: EvidenceBundle) -> list[str]:
    """Extract domains that have test coverage."""
    # This is a placeholder — in production, this would query test coverage data
    return list(bundle.domains)[:3] if bundle.domains else []


def _extract_missing_tests(
    bundle: EvidenceBundle,
    understanding: ChangeUnderstanding,
) -> list[str]:
    """Identify missing test coverage from evidence."""
    missing: list[str] = []

    # Check for cross-domain gaps
    cross_domain = [
        ev for ev in bundle.impact_evidence
        if ev.evidence_type and "cross" in ev.evidence_type.lower()
    ]
    if cross_domain:
        for ev in cross_domain[:2]:
            try:
                source = ev.source.name if hasattr(ev.source, "name") else ""
                target = ev.target.name if hasattr(ev.target, "name") else ""
                if source and target:
                    missing.append(f"{source} → {target} integration test")
            except Exception:
                continue

    # Check for risk anchor gaps
    for ra in bundle.risk_anchors[:2]:
        try:
            symbol = ra.symbol if hasattr(ra, "symbol") else ""
            if symbol:
                missing.append(f"{symbol} risk scenario coverage")
        except Exception:
            continue

    return missing


def _extract_known_assumptions(bundle: EvidenceBundle) -> list[str]:
    """Extract assumptions from constraints and evidence."""
    assumptions: list[str] = []

    for c in bundle.constraints:
        try:
            if hasattr(c, "description") and c.description:
                assumptions.append(c.description)
        except Exception:
            continue

    if not assumptions:
        assumptions.append("Downstream consumers handle updated values correctly")

    return assumptions


def _compute_deterministic_verdict(bundle: EvidenceBundle) -> str:
    """Compute the deterministic verdict from evidence."""
    if bundle.risk_anchors:
        return "REVIEW_REQUIRED"
    if bundle.impact_evidence:
        high_conf = [ev for ev in bundle.impact_evidence if ev.confidence >= 0.8]
        if high_conf:
            return "REVIEW_REQUIRED"
    return "NO_SIGNIFICANT_PROPAGATION_FOUND"


def _detect_language(bundle: EvidenceBundle) -> str:
    """Detect programming language from evidence."""
    # Placeholder — in production, this comes from the source adapter
    return "Python"


def _detect_framework(bundle: EvidenceBundle) -> str:
    """Detect framework from evidence."""
    # Placeholder — in production, this comes from the source adapter
    return "FastAPI"
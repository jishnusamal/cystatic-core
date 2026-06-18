"""
CI Coverage Gap Detector — "Why CI Missed This" Engine.

Defines CI coverage axes and classifies each anchor into coverage domains.
Generates deterministic explanations for why CI would/wouldn't catch a failure.

Mechanisms:
1. CI coverage axes:
   - Unit scope: function-level tests
   - Integration scope: service-to-service
   - Behavioral scope: cross-flow correctness
2. For each anchor:
   - Classify into coverage domain
   - Check CI visibility
   - Generate explanation
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ── CI Coverage Axes ─────────────────────────────────────────────────────

@dataclass
class CoverageAxis:
    """A CI coverage axis with its properties."""
    name: str
    description: str
    visibility_levels: dict[str, str]  # domain_type -> visibility

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "visibility_levels": self.visibility_levels,
        }


# The three axes
UNIT_SCOPE = CoverageAxis(
    name="unit_scope",
    description="Function-level tests verifying individual logic units",
    visibility_levels={
        "local_logic": "HIGH",
        "cross_service": "LOW",
        "runtime_state_mutation": "LOW",
        "external_dependency": "ZERO",
    },
)

INTEGRATION_SCOPE = CoverageAxis(
    name="integration_scope",
    description="Service-to-service interaction tests",
    visibility_levels={
        "local_logic": "MEDIUM",
        "cross_service": "HIGH",
        "runtime_state_mutation": "MEDIUM",
        "external_dependency": "LOW",
    },
)

BEHAVIORAL_SCOPE = CoverageAxis(
    name="behavioral_scope",
    description="Cross-flow correctness tests (end-to-end scenarios)",
    visibility_levels={
        "local_logic": "MEDIUM",
        "cross_service": "MEDIUM",
        "runtime_state_mutation": "HIGH",
        "external_dependency": "HIGH",
    },
)

ALL_AXES: list[CoverageAxis] = [UNIT_SCOPE, INTEGRATION_SCOPE, BEHAVIORAL_SCOPE]


# ── Coverage domains ─────────────────────────────────────────────────────

_COVERAGE_DOMAIN_PATTERNS: list[tuple[set[str], str]] = [
    # local_logic: pure computation, data transformation, formatting
    ({"calculate", "compute", "format", "validate", "parse", "convert",
      "transform", "normalize", "sanitize", "round", "truncate"}, "local_logic"),
    # cross_service: service calls, API requests, network I/O
    ({"service", "api", "client", "request", "http", "webhook",
      "callback", "endpoint", "route", "handler", "controller"}, "cross_service"),
    # runtime_state_mutation: state changes, transitions, side effects
    ({"state", "status", "transition", "save", "update", "delete",
      "insert", "persist", "commit", "flush", "toggle", "flag"}, "runtime_state_mutation"),
    # external_dependency: third-party integrations, payment gateways, tax providers
    ({"payment", "gateway", "stripe", "braintree", "paypal", "adyen",
      "taxjar", "avalara", "vertex", "shipstation", "easyPost",
      "sendgrid", "twilio", "s3", "sqs", "ses", "kafka"}, "external_dependency"),
]

_FUNCTION_BODY_MUTATION_PATTERNS: list[str] = [
    ".save(", ".update(", ".delete(", ".insert(", ".commit(",
    "state =", "status =",
    "db.", "session.", "cache.", "redis.",
]

_FUNCTION_BODY_SERVICE_PATTERNS: list[str] = [
    ".post(", ".get(", ".put(", ".delete(", ".patch(",
    "requests.", "httpx.", "client.",
    "webhook", "callback",
]

_FUNCTION_BODY_EXTERNAL_PATTERNS: list[str] = [
    "stripe.", "braintree.", "paypal.", "adyen.",
    "taxjar.", "avalara.", "vertex.",
    "sendgrid.", "twilio.", "s3.", "sqs.", "ses.",
    "kafka.", "pubsub.", "event.",
]


def _classify_coverage_domain(
    symbol: str,
    tags: list[str],
    hunks: list[dict] | None = None,
) -> str:
    """Classify a symbol into a coverage domain.

    Domains (ordered by specificity):
    - external_dependency: touches third-party integrations
    - runtime_state_mutation: changes state (save/update/delete)
    - cross_service: calls other services
    - local_logic: pure computation

    The first match wins (most specific first).
    """
    combined = f"{symbol.lower()} {' '.join(t.lower() for t in tags)}"

    # 1. Check for external dependency patterns (most specific)
    for pattern_set, domain in _COVERAGE_DOMAIN_PATTERNS:
        if domain != "external_dependency":
            continue
        if any(p in combined for p in pattern_set):
            return domain

    # Check function body for external patterns
    if hunks:
        for hunk in hunks:
            lines = hunk.get("lines", []) if isinstance(hunk, dict) else []
            for line in lines:
                content = line.get("content", "") if isinstance(line, dict) else str(line)
                lower = content.lower()
                for pattern in _FUNCTION_BODY_EXTERNAL_PATTERNS:
                    if pattern in lower:
                        return "external_dependency"

    # 2. Check for runtime_state_mutation
    for pattern_set, domain in _COVERAGE_DOMAIN_PATTERNS:
        if domain != "runtime_state_mutation":
            continue
        if any(p in combined for p in pattern_set):
            return domain

    if hunks:
        for hunk in hunks:
            lines = hunk.get("lines", []) if isinstance(hunk, dict) else []
            for line in lines:
                content = line.get("content", "") if isinstance(line, dict) else str(line)
                lower = content.lower()
                for pattern in _FUNCTION_BODY_MUTATION_PATTERNS:
                    if pattern in lower:
                        return "runtime_state_mutation"

    # 3. Check for cross_service
    for pattern_set, domain in _COVERAGE_DOMAIN_PATTERNS:
        if domain != "cross_service":
            continue
        if any(p in combined for p in pattern_set):
            return domain

    if hunks:
        for hunk in hunks:
            lines = hunk.get("lines", []) if isinstance(hunk, dict) else []
            for line in lines:
                content = line.get("content", "") if isinstance(line, dict) else str(line)
                lower = content.lower()
                for pattern in _FUNCTION_BODY_SERVICE_PATTERNS:
                    if pattern in lower:
                        return "cross_service"

    # 4. Check for local_logic (least specific)
    for pattern_set, domain in _COVERAGE_DOMAIN_PATTERNS:
        if domain != "local_logic":
            continue
        if any(p in combined for p in pattern_set):
            return domain

    # Default: classify based on file path
    return "local_logic"


def _get_ci_visibility(
    coverage_domain: str,
    axes: list[CoverageAxis] | None = None,
) -> list[dict[str, str]]:
    """Get CI visibility for a coverage domain across all axes.

    Returns list of {axis: str, visibility: str} for each axis.
    """
    axes = axes or ALL_AXES
    results: list[dict[str, str]] = []
    for axis in axes:
        visibility = axis.visibility_levels.get(coverage_domain, "UNKNOWN")
        results.append({
            "axis": axis.name,
            "visibility": visibility,
        })
    return results


def _build_explanation(
    symbol: str,
    coverage_domain: str,
    visibilities: list[dict[str, str]],
) -> str:
    """Build a human-readable explanation for CI gap.

    Uses templates based on coverage domain and visibility levels.
    """
    # Find lowest visibility
    visibility_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2, "ZERO": 3, "UNKNOWN": 4}
    lowest = min(visibilities, key=lambda v: visibility_order.get(v["visibility"], 4))

    domain_descriptions = {
        "local_logic": "local computation/transformation logic",
        "cross_service": "cross-service interaction",
        "runtime_state_mutation": "runtime state mutation / side effect",
        "external_dependency": "external provider integration",
    }

    domain_desc = domain_descriptions.get(coverage_domain, coverage_domain)

    if lowest["visibility"] == "ZERO":
        return (
            f"CI has ZERO visibility into {symbol}'s {domain_desc}. "
            f"No test scope covers {domain_desc}. "
            "This is completely invisible to the current CI pipeline."
        )
    elif lowest["visibility"] == "LOW":
        return (
            f"CI only partially validates {symbol}'s {domain_desc}. "
            f"The {lowest['axis']} axis has LOW coverage for {coverage_domain}. "
            "Changes in this area may slip through unit tests."
        )
    elif lowest["visibility"] == "MEDIUM":
        return (
            f"CI has moderate visibility into {symbol}'s {domain_desc}. "
            f"The {lowest['axis']} axis provides partial coverage. "
            "Some failure modes may be undetected."
        )
    else:
        return (
            f"CI has HIGH visibility into {symbol}'s {domain_desc}. "
            "Changes in this area are likely caught by existing tests."
        )


# ═══════════════════════════════════════════════════════════════════════════
# Main: Analyze CI coverage gaps
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class AnchorGapAnalysis:
    """CI gap analysis for a single anchor (symbol)."""
    symbol: str
    file_path: str = ""
    coverage_domain: str = "local_logic"
    ci_visibility: list[dict[str, str]] = field(default_factory=list)
    explanation: str = ""
    risk_of_ci_missing: str = "MEDIUM"  # HIGH | MEDIUM | LOW
    ai_suggests_human_review: bool = False
    failure_class: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "file_path": self.file_path,
            "coverage_domain": self.coverage_domain,
            "ci_visibility": self.ci_visibility,
            "explanation": self.explanation,
            "risk_of_ci_missing": self.risk_of_ci_missing,
            "ai_suggests_human_review": self.ai_suggests_human_review,
            "failure_class": self.failure_class,
        }


def analyze_anchor(
    symbol: str,
    tags: list[str] | None = None,
    hunks: list[dict] | None = None,
    file_path: str = "",
    failure_class: str = "",
) -> AnchorGapAnalysis:
    """Analyze CI coverage gap for a single anchor.

    Args:
        symbol: The symbol name.
        tags: Semantic tags.
        hunks: Diff hunks.
        file_path: Full file path.
        failure_class: Optional failure class from failure simulation.

    Returns:
        AnchorGapAnalysis with classification, visibility, and explanation.
    """
    tags = tags or []
    coverage_domain = _classify_coverage_domain(symbol, tags, hunks)
    visibilities = _get_ci_visibility(coverage_domain)
    explanation = _build_explanation(symbol, coverage_domain, visibilities)

    # Compute risk of CI missing this
    visibility_levels = {v["axis"]: v["visibility"] for v in visibilities}
    risk_map = {"ZERO": "HIGH", "LOW": "HIGH", "MEDIUM": "MEDIUM", "HIGH": "LOW"}
    worst_visibility = min(
        visibilities,
        key=lambda v: {"HIGH": 0, "MEDIUM": 1, "LOW": 2, "ZERO": 3, "UNKNOWN": 4}.get(v["visibility"], 4),
    )
    risk = risk_map.get(worst_visibility["visibility"], "MEDIUM")

    # Suggest human review for ZERO or LOW visibility domains
    needs_review = worst_visibility["visibility"] in ("ZERO", "LOW")

    return AnchorGapAnalysis(
        symbol=symbol,
        file_path=file_path,
        coverage_domain=coverage_domain,
        ci_visibility=visibilities,
        explanation=explanation,
        risk_of_ci_missing=risk,
        ai_suggests_human_review=needs_review,
        failure_class=failure_class,
    )


def analyze_batch(
    enriched_files: list[dict],
    failure_classes: dict[str, str] | None = None,
) -> list[AnchorGapAnalysis]:
    """Analyze CI coverage gaps for all anchors in enriched files.

    Args:
        enriched_files: Enriched file data from orchestrator.
        failure_classes: Optional map of symbol -> failure class.

    Returns:
        List of AnchorGapAnalysis objects.
    """
    failure_classes = failure_classes or {}
    results: list[AnchorGapAnalysis] = []

    for file_data in enriched_files:
        file_path = file_data.get("file_path", "")
        for fn in file_data.get("changed_functions", []) or []:
            fn_data = fn if isinstance(fn, dict) else {}
            symbol = fn_data.get("name", "")
            if not symbol:
                continue

            # Collect tags
            tags: list[str] = []
            for signal in file_data.get("keyword_signals", []) or []:
                signal_text = signal.keyword if hasattr(signal, "keyword") else str(signal)
                tags.append(signal_text.lower())

            analysis = analyze_anchor(
                symbol=symbol,
                tags=tags,
                hunks=file_data.get("hunks"),
                file_path=file_path,
                failure_class=failure_classes.get(symbol, ""),
            )
            results.append(analysis)

    # Sort by risk (HIGH first)
    risk_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    results.sort(key=lambda a: risk_order.get(a.risk_of_ci_missing, 3))
    return results


def generate_coverage_report(
    enriched_files: list[dict],
    failure_classes: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Generate a complete CI coverage gap report.

    Args:
        enriched_files: Enriched file data from orchestrator.
        failure_classes: Optional map of symbol -> failure class.

    Returns:
        Dict with 'analyses', 'summary', 'recommendations' keys.
    """
    analyses = analyze_batch(enriched_files, failure_classes)

    # Summary stats
    total = len(analyses)
    high_risk = sum(1 for a in analyses if a.risk_of_ci_missing == "HIGH")
    medium_risk = sum(1 for a in analyses if a.risk_of_ci_missing == "MEDIUM")
    needs_review = sum(1 for a in analyses if a.ai_suggests_human_review)

    # Domain breakdown
    domain_counts: dict[str, int] = {}
    for a in analyses:
        domain_counts[a.coverage_domain] = domain_counts.get(a.coverage_domain, 0) + 1

    # Recommendations
    recommendations: list[str] = []
    if high_risk > 0:
        recommendations.append(
            f"Add integration tests for {high_risk} high-risk symbols "
            "that involve external dependencies or state mutations."
        )
    if needs_review > 0:
        recommendations.append(
            f"Manual review recommended for {needs_review} symbols "
            "with LOW or ZERO CI visibility."
        )
    if domain_counts.get("external_dependency", 0) > 0:
        recommendations.append(
            "External dependency changes require mock-based integration tests "
            "in the CI pipeline."
        )
    if domain_counts.get("runtime_state_mutation", 0) > 0:
        recommendations.append(
            "State mutation changes need behavioral (end-to-end) test coverage."
        )

    summary = {
        "total_anchors": total,
        "high_risk_count": high_risk,
        "medium_risk_count": medium_risk,
        "needs_human_review": needs_review,
        "domain_breakdown": domain_counts,
    }

    return {
        "analyses": [a.to_dict() for a in analyses],
        "summary": summary,
        "recommendations": recommendations,
        "coverage_axes": [a.to_dict() for a in ALL_AXES],
    }
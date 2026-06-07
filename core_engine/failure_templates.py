"""
Failure Templates — productized intelligence primitives.

These are NOT generic risk patterns. These are concrete failure classes
that the system uses to generate structured failure hypotheses.

Without these, the LLM invents random failure modes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import re


@dataclass
class FailureTemplate:
    """A template for a specific failure class."""
    name: str
    description: str
    trigger_patterns: list[str]  # patterns that might trigger this failure
    evidence_required: list[str]  # types of evidence needed to confirm
    severity: str  # CRITICAL | HIGH | MEDIUM | LOW
    production_impact_template: str  # template with {placeholders}
    system_regions: list[str] = field(default_factory=list)


# ----- DEFINED FAILURE TEMPLATES -----

FAILURE_TEMPLATES: list[FailureTemplate] = [
    FailureTemplate(
        name="idempotency_break",
        description="A change breaks idempotency guarantees, causing duplicate processing on retry.",
        trigger_patterns=[
            "removed idempotency check",
            "removed duplicate detection",
            "removed dedup",
            "removed idempotent",
            "removed retry guard",
            "removed unique constraint",
            "removed 'if already processed'",
            "missing idempotency_key",
        ],
        evidence_required=["function_change", "data_access_pattern"],
        severity="HIGH",
        production_impact_template="Retried {operation} produces {effect} instead of being safely idempotent",
        system_regions=["payment", "billing", "webhook", "order"],
    ),
    FailureTemplate(
        name="double_charge_double_write",
        description="A customer is charged twice or a record is written twice due to missing guards.",
        trigger_patterns=[
            "double charge",
            "double write",
            "duplicate charge",
            "charge twice",
            "missing idempotency",
            "removed dedup check",
            "removed duplicate prevention",
            "multiple charges",
        ],
        evidence_required=["payment_function", "charge_call", "data_write"],
        severity="CRITICAL",
        production_impact_template="Customer {customer} is charged {amount} multiple times for {reason}",
        system_regions=["payment", "billing", "checkout"],
    ),
    FailureTemplate(
        name="null_propagation",
        description="A nullable value is not checked before use, causing null pointer / type errors in production.",
        trigger_patterns=[
            "missing null check",
            "removed None check",
            "removed null guard",
            "removed optional handling",
            "removed None return",
            "missing None",
            "removed .get(",
            "removed default",
        ],
        evidence_required=["function_change", "optional_access"],
        severity="HIGH",
        production_impact_template="{function} raises NullReference/TypeError when {field} is None in production",
        system_regions=["core", "data", "api"],
    ),
    FailureTemplate(
        name="stale_cache",
        description="Cache invalidation is removed or never added, causing stale data served to users.",
        trigger_patterns=[
            "removed cache invalidate",
            "removed cache clear",
            "removed cache delete",
            "removed cache bust",
            "missing cache invalidation",
            "removed cache.update",
            "cache TTL extended",
            "removed cache refresh",
        ],
        evidence_required=["cache_access", "data_write"],
        severity="MEDIUM",
        production_impact_template="Users see stale {data_type} for up to {duration} because {cache_key} was never invalidated",
        system_regions=["core", "api", "notification"],
    ),
    FailureTemplate(
        name="partial_update_drift",
        description="A partial update to one data source without updating its dependent sources causes data drift.",
        trigger_patterns=[
            "partial update",
            "missing update",
            "update only one",
            "updated but not",
            "update without",
            "missing sync",
            "drift",
            "inconsistent update",
        ],
        evidence_required=["data_write", "data_read"],
        severity="HIGH",
        production_impact_template="{primary} is updated but {dependent} is not, causing data drift between systems",
        system_regions=["checkout", "order", "invoice", "billing"],
    ),
    FailureTemplate(
        name="silent_fallback_activation",
        description="A fallback path activates silently, masking failures and causing incorrect behavior.",
        trigger_patterns=[
            "fallback",
            "except",
            "try catch",
            "on_error",
            "default value",
            "catch all",
            "silent fallback",
            "empty except",
        ],
        evidence_required=["error_handling_change"],
        severity="MEDIUM",
        production_impact_template="{error} is silently swallowed by {fallback}, hiding the real issue",
        system_regions=["core", "api", "payment", "webhook"],
    ),
    FailureTemplate(
        name="auth_bypass_chain",
        description="An authentication or authorization check is removed, weakened, or bypassable.",
        trigger_patterns=[
            "removed auth check",
            "removed permission",
            "removed authentication",
            "bypassed auth",
            "removed login_required",
            "removed authorize",
            "removed permission check",
            "weakened auth",
            "removed guard",
        ],
        evidence_required=["auth_function"],
        severity="CRITICAL",
        production_impact_template="Unauthenticated user can access {protected_resource} because {auth_check} was removed",
        system_regions=["auth", "authentication", "api"],
    ),
    FailureTemplate(
        name="tax_billing_mismatch",
        description="Tax calculation or breakdown logic changes cause incorrect tax amounts on invoices/orders.",
        trigger_patterns=[
            "tax breakdown",
            "tax calculation",
            "tax rate",
            "tax amount",
            "tax changed",
            "tax logic",
            "vat",
            "gst",
            "tax code",
        ],
        evidence_required=["tax_function", "financial_calculation"],
        severity="HIGH",
        production_impact_template="Tax on {invoice} is {incorrect_amount} instead of {expected_amount}, causing {compliance_issue}",
        system_regions=["tax", "invoice", "billing", "checkout"],
    ),
    FailureTemplate(
        name="logic_negation_flip",
        description="A boolean condition or comparison was inverted, causing opposite behavior.",
        trigger_patterns=[
            "!=",
            "not ",
            "!= True",
            "== False",
            "inverted",
            "flipped",
            "negation",
            "reversed condition",
            "from > to <",
            "from True to False",
        ],
        evidence_required=["condition_change"],
        severity="HIGH",
        production_impact_template="{condition} was inverted, causing {opposite_behavior} when {trigger_condition}",
        system_regions=["core", "all"],
    ),
    FailureTemplate(
        name="data_validation_removed",
        description="Input validation was removed or weakened, allowing malformed data through.",
        trigger_patterns=[
            "removed validation",
            "removed validate",
            "removed check",
            "removed assert",
            "removed raise",
            "removed error handling",
            "removed type check",
            "bypassed validation",
        ],
        evidence_required=["validation_function"],
        severity="HIGH",
        production_impact_template="Malformed {input_type} reaches {system} because {validation} was removed, causing {failure}",
        system_regions=["core", "api"],
    ),
    FailureTemplate(
        name="async_event_mismatch",
        description="An event payload or schema changed but consumers weren't updated, causing silent drops.",
        trigger_patterns=[
            "event changed",
            "payload changed",
            "schema changed",
            "message format",
            "event payload",
            "webhook payload",
            "removed field",
            "added field",
        ],
        evidence_required=["event_emission", "event_consumption"],
        severity="MEDIUM",
        production_impact_template="{consumer} receives {event} with unexpected {field} because {reason}",
        system_regions=["webhook", "notification", "async"],
    ),
    FailureTemplate(
        name="state_inconsistency",
        description="A state transition was changed, allowing invalid state combinations.",
        trigger_patterns=[
            "state changed",
            "status changed",
            "transition",
            "state machine",
            "state removed",
            "added state",
            "state transition",
            "removed status",
        ],
        evidence_required=["state_function", "business_logic"],
        severity="HIGH",
        production_impact_template="{entity} enters invalid state {state} because {transition} was changed",
        system_regions=["order", "subscription", "checkout", "payment"],
    ),
]


def get_failure_template(name: str) -> FailureTemplate | None:
    """Get a failure template by name."""
    for template in FAILURE_TEMPLATES:
        if template.name == name:
            return template
    return None


def match_failure_templates(
    risk_patterns: list[Any],
    enriched_files: list[dict],
    behavior_diffs: list[Any] | None = None,
) -> list[dict[str, Any]]:
    """
    Match failure templates against detected risk patterns and changed code.

    Returns list of matched template instances with confidence scores.
    """
    matches: list[dict[str, Any]] = []

    # Collect all changed line content
    changed_lines = _collect_changed_lines(enriched_files)

    # Collect all risk pattern types
    risk_types = set()
    for rp in risk_patterns:
        rp_data = _as_dict(rp)
        event_type = str(rp_data.get("type", "")).lower()
        risk_types.add(event_type)

    # Collect all changed function names
    changed_functions = _collect_changed_functions(enriched_files)
    changed_function_names = {fn.get("name", "").lower() for fn in changed_functions if fn.get("name")}

    for template in FAILURE_TEMPLATES:
        match_score = 0.0
        matched_triggers: list[str] = []
        matched_regions: list[str] = []
        evidence_found: list[str] = []

        # Check trigger patterns against changed lines
        for line in changed_lines:
            line_lower = line.lower()
            for pattern in template.trigger_patterns:
                if pattern.lower() in line_lower:
                    match_score += 0.2
                    matched_triggers.append(pattern)
                    break  # count once per line

        # Check risk pattern alignment
        for risk_type in risk_types:
            for trigger in template.trigger_patterns:
                normalized_trigger = trigger.replace(" ", "_").lower()
                if normalized_trigger in risk_type or risk_type in normalized_trigger:
                    match_score += 0.15
                    matched_triggers.append(risk_type)
                    break

        # Check function name alignment
        for fn_name in changed_function_names:
            for region in template.system_regions:
                if region.lower() in fn_name:
                    matched_regions.append(region)
                    match_score += 0.1
                    break

        # Check system region alignment
        for file_data in enriched_files:
            file_path = str(file_data.get("file_path", "")).lower()
            for region in template.system_regions:
                if region.lower() in file_path:
                    matched_regions.append(region)
                    match_score += 0.05
                    break

        # Cap match score
        match_score = min(match_score, 1.0)

        if match_score >= 0.2:
            matches.append({
                "template_name": template.name,
                "description": template.description,
                "severity": template.severity,
                "confidence": round(match_score, 2),
                "matched_triggers": list(set(matched_triggers))[:5],
                "matched_system_regions": list(set(matched_regions)),
                "production_impact_template": template.production_impact_template,
            })

    # Sort by confidence descending
    matches.sort(key=lambda m: -m["confidence"])
    return matches


def _collect_changed_lines(enriched_files: list[dict]) -> list[str]:
    """Collect all changed line contents from enriched files."""
    lines: list[str] = []
    for file_data in enriched_files:
        for hunk in file_data.get("hunks", []) or []:
            hunk_data = _as_dict(hunk)
            for raw_line in hunk_data.get("lines", []) or []:
                line_data = _as_dict(raw_line)
                content = str(line_data.get("content", "")).strip()
                if content and not content.startswith("#"):
                    lines.append(content)
    return lines


def _collect_changed_functions(enriched_files: list[dict]) -> list[dict[str, Any]]:
    """Collect all changed functions from enriched files."""
    functions: list[dict[str, Any]] = []
    for file_data in enriched_files:
        for fn in file_data.get("changed_functions", []) or []:
            fn_data = _as_dict(fn)
            if fn_data.get("name"):
                functions.append(fn_data)
    return functions


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return {}
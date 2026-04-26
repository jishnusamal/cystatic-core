from __future__ import annotations

from typing import Any

from core_engine.risk_flags import RiskEventType


class FailureSimulator:
    """
    Deterministic text generator that translates risk patterns into
    concrete failure-mode narratives for reviewers.
    """

    def generate(self, risk_patterns: list[Any], enriched_files: list[dict]) -> list[str]:
        del enriched_files  # reserved for future context-aware expansions

        lines: list[str] = []
        for risk in risk_patterns or []:
            risk_dict = self._as_dict(risk)
            event_type = str(risk_dict.get("type", ""))
            trigger = str(risk_dict.get("trigger", "")).strip()
            reason = str(risk_dict.get("reason", "")).strip()
            file_path = str(risk_dict.get("file_path", "")).strip()
            function = str(risk_dict.get("function", "")).strip()

            scenario = self._scenario_for(event_type)
            if not scenario:
                continue

            location = file_path
            if function:
                location = f"{file_path}::{function}" if file_path else function

            summary = scenario
            if trigger:
                summary = f"{summary} Trigger: {trigger}."
            elif reason:
                summary = f"{summary} Trigger: {reason}."
            if location:
                summary = f"{summary} Location: {location}."

            lines.append(summary)

        return lines

    def _scenario_for(self, event_type: str) -> str:
        scenarios = {
            RiskEventType.AUTH_BYPASS.value: "Unauthorized users may access protected actions.",
            RiskEventType.PERMISSION_REMOVED.value: "Authorization boundaries may be weaker than intended.",
            RiskEventType.FINANCIAL_LOGIC_CHANGE.value: "Payment outcomes may diverge from expected business rules.",
            RiskEventType.FINANCIAL_DATA_MODEL_CHANGE.value: "Financial records may deserialize or aggregate incorrectly.",
            RiskEventType.TAX_CALCULATION_CHANGE.value: "Tax totals may be miscomputed across checkout and invoicing.",
            RiskEventType.SCHEMA_MIGRATION.value: "Deployment may fail or leave schema partially applied.",
            RiskEventType.DATA_BACKFILL.value: "Backfill may rewrite historical financial data incorrectly.",
            RiskEventType.INVOICE_RENDERING_CHANGE.value: "Invoice output may show incorrect or incomplete tax lines.",
            RiskEventType.DATA_LEAK_RISK.value: "Sensitive data may be exposed through responses or logs.",
            RiskEventType.STATE_INCONSISTENCY.value: "User/account state may become inconsistent across services.",
            RiskEventType.BACKDOOR_INTRODUCED.value: "Hardcoded access path may allow unauthorized entry.",
            RiskEventType.VALIDATION_REMOVED.value: "Invalid input may propagate into core workflows.",
            RiskEventType.CRITICAL_DEPENDENCY_CHANGED.value: "Runtime behavior may change due to dependency drift.",
        }
        return scenarios.get(event_type, "")

    def _as_dict(self, value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        if hasattr(value, "model_dump"):
            return value.model_dump()
        return {}

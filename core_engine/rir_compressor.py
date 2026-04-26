from __future__ import annotations

from typing import Any


class RIRCompressor:
    """
    Compresses analysis output into a high-signal Reasoning IR payload
    intended for LLM reasoning with low token cost.
    """

    def compress(
        self,
        enriched_files: list[dict],
        risk_patterns: list[Any] | None = None,
        entry_points_affected: list[Any] | None = None,
    ) -> dict[str, Any]:
        flows = self._collect_flows(enriched_files)
        risk_events = self._collect_risk_events(risk_patterns or [])
        changed_functions = self._collect_changed_functions(enriched_files)
        entry_points = self._collect_entry_points(entry_points_affected or [])

        return {
            "flows": flows,
            "risk_events": risk_events,
            "changed_functions": changed_functions,
            "entry_points": entry_points,
            "execution_path_hint": self._build_execution_path_hint(
                flows=flows,
                risk_events=risk_events,
                changed_functions=changed_functions,
            ),
        }

    def _collect_flows(self, enriched_files: list[dict]) -> list[str]:
        values: set[str] = set()
        for file_data in enriched_files:
            for flow in file_data.get("flows", []) or []:
                values.add(self._enum_or_string(flow))
        return sorted(v for v in values if v)

    def _collect_risk_events(self, risk_patterns: list[Any]) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        seen: set[tuple[str, str, float]] = set()

        for risk in risk_patterns:
            data = self._as_dict(risk)
            event_type = self._enum_or_string(data.get("type"))
            context = str(data.get("reason", "") or "").strip()
            confidence_raw = data.get("confidence", 0.9)
            confidence = float(confidence_raw) if isinstance(confidence_raw, (int, float)) else 0.9
            key = (event_type, context, confidence)
            if not event_type or key in seen:
                continue
            seen.add(key)
            events.append(
                {
                    "type": event_type,
                    "context": context,
                    "confidence": confidence,
                }
            )
        return events

    def _collect_changed_functions(self, enriched_files: list[dict]) -> list[str]:
        names: set[str] = set()
        for file_data in enriched_files:
            for fn in file_data.get("changed_functions", []) or []:
                fn_data = self._as_dict(fn)
                name = str(fn_data.get("name", "")).strip()
                if name and self._is_execution_critical_function(name):
                    names.add(name)
        return sorted(names)

    def _collect_entry_points(self, entry_points_affected: list[Any]) -> list[str]:
        routes: set[str] = set()
        for ep in entry_points_affected:
            ep_data = self._as_dict(ep)
            route = str(ep_data.get("route", "")).strip()
            if route:
                routes.add(route)
        return sorted(routes)

    def _enum_or_string(self, value: Any) -> str:
        if value is None:
            return ""
        if hasattr(value, "value"):
            return str(getattr(value, "value"))
        return str(value)

    def _as_dict(self, value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        if hasattr(value, "model_dump"):
            return value.model_dump()
        return {}

    def _is_execution_critical_function(self, name: str) -> bool:
        lowered = name.lower()

        # Drop obvious tests.
        if lowered.startswith("test") or ".test" in lowered:
            return False

        # Drop helper/plumbing utilities unless they look domain-critical.
        helper_prefixes = ("_build_", "_from_", "_to_", "_parse_", "_serialize_", "_deserialize_")
        base_name = lowered.split(".")[-1]
        if any(base_name.startswith(prefix) for prefix in helper_prefixes):
            domain_markers = ("checkout", "payment", "order", "invoice", "tax", "billing", "subscription")
            return any(marker in lowered for marker in domain_markers)

        utility_markers = ("util", "helper", "fixture", "factory", "mock", "stub")
        if any(marker in lowered for marker in utility_markers):
            return False

        # Keep business/system-boundary functions.
        critical_markers = ("checkout", "payment", "order", "invoice", "tax", "billing", "subscription", "charge")
        if any(marker in lowered for marker in critical_markers):
            return True

        # Keep methods that belong to service/model aggregates by convention.
        if "." in name:
            owner = lowered.split(".")[0]
            if any(token in owner for token in ("service", "order", "checkout", "invoice")):
                return True

        return False

    def _build_execution_path_hint(
        self,
        flows: list[str],
        risk_events: list[dict[str, Any]],
        changed_functions: list[str],
    ) -> list[str]:
        steps: list[str] = []

        def add(step: str) -> None:
            if step not in steps:
                steps.append(step)

        joined_functions = " ".join(changed_functions).lower()
        event_types = {str(evt.get("type", "")) for evt in risk_events}

        if "authentication_flow" in flows or "AUTH_BYPASS" in event_types:
            add("authentication")
            add("session handling")

        if "payment_processing" in flows:
            add("checkout")
            add("payment processing")

        if any(evt in event_types for evt in ("TAX_CALCULATION_CHANGE", "FINANCIAL_LOGIC_CHANGE")):
            add("tax calculation")

        if "order" in joined_functions:
            add("order creation")

        if any(evt in event_types for evt in ("INVOICE_RENDERING_CHANGE",)) or "invoice" in joined_functions:
            add("invoice generation")

        if not steps:
            add("core business flow")

        return steps

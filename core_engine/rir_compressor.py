from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core_engine.behavior_diff_builder import BehaviorDiff, build_behavior_diffs
from core_engine.factor_ir_v3 import build_factor_ir_v3


@dataclass
class Evidence:
    """Concrete evidence supporting a reasoning artifact."""
    type: str  # function, file, line, call, import
    value: str
    source: str  # file_path where evidence was found


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
        """Legacy multi-view IR — kept for persistence/debugging, not sent to LLM."""
        flows = self._collect_flows(enriched_files)
        risk_events = self._collect_risk_events(risk_patterns or [])
        changed_functions = self._collect_changed_functions(enriched_files)
        entry_points = self._collect_entry_points(entry_points_affected or [])
        
        # Phase 1: Evidence preservation
        evidence = self._collect_evidence(enriched_files)
        changed_symbols = self._collect_changed_symbols(enriched_files)
        changed_lines = self._collect_changed_lines(enriched_files)

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
            "change_summaries": self._build_change_summaries(enriched_files),
            # Phase 1 additions
            "evidence": [e.__dict__ for e in evidence],
            "changed_symbols": changed_symbols,
            "changed_lines": changed_lines,
        }

    def compress_v3(
        self,
        enriched_files: list[dict],
        risk_patterns: list[Any] | None = None,
        entry_points_affected: list[Any] | None = None,
        behavior_diffs: list[BehaviorDiff] | None = None,
    ) -> dict[str, Any]:
        """Canonical Factor IR v3 — the only payload sent to the LLM."""
        diffs = behavior_diffs if behavior_diffs is not None else build_behavior_diffs(enriched_files)
        return build_factor_ir_v3(
            enriched_files=enriched_files,
            behavior_diffs=diffs,
            entry_points_affected=entry_points_affected,
            risk_patterns=risk_patterns,
        )

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

    def _build_change_summaries(self, enriched_files: list[dict]) -> list[dict[str, str]]:
        summaries: list[dict[str, str]] = []
        seen: set[tuple[str, str]] = set()

        for file_data in enriched_files:
            file_path = str(file_data.get("file_path", "")).strip()
            changed_functions = file_data.get("changed_functions", []) or []

            for fn in changed_functions:
                fn_data = self._as_dict(fn)
                function_name = str(fn_data.get("name", "")).strip()
                if not function_name or not self._is_execution_critical_function(function_name):
                    continue

                key = (file_path, function_name)
                if key in seen:
                    continue
                seen.add(key)

                summary, risk_relevance = self._summarize_change(file_path, function_name)
                summaries.append(
                    {
                        "file": file_path,
                        "function": function_name,
                        "summary": summary,
                        "risk_relevance": risk_relevance,
                    }
                )

        return summaries

    def _summarize_change(self, file_path: str, function_name: str) -> tuple[str, str]:
        lowered_file = file_path.lower()
        lowered_fn = function_name.lower()
        domain_text = f"{lowered_file} {lowered_fn}"

        if "checkout" in domain_text and "tax" in domain_text:
            return (
                "Checkout tax handling logic changed and likely relies on updated tax breakdown fields.",
                "Incorrect breakdown mapping can produce wrong checkout tax totals.",
            )

        if "invoice" in domain_text and ("total" in domain_text or "render" in domain_text or "item" in domain_text):
            return (
                "Invoice totals/rendering logic changed to use revised tax item composition.",
                "Invoices may show incorrect or duplicated tax lines.",
            )

        if "order" in domain_text and ("create" in domain_text or "from_checkout" in domain_text):
            return (
                "Order creation path changed and now persists updated checkout tax-related fields.",
                "Order tax data can drift from checkout tax data if field mapping is inconsistent.",
            )

        if "payment" in domain_text or "charge" in domain_text:
            return (
                "Payment processing logic changed in a business-critical execution path.",
                "Payment status or amount handling can diverge from expected outcomes.",
            )

        if "tax" in domain_text:
            return (
                "Tax computation or propagation logic changed in this function.",
                "Tax totals can become inaccurate across checkout/order/invoice flows.",
            )

        return (
            "Business-critical function changed in the current execution path.",
            "Behavioral regressions in this function can impact downstream workflows.",
        )

    # Phase 1: Evidence preservation methods
    def _collect_evidence(self, enriched_files: list[dict]) -> list[Evidence]:
        """Collect concrete evidence from the PR changes."""
        evidence: list[Evidence] = []
        
        for file_data in enriched_files:
            file_path = str(file_data.get("file_path", ""))
            if not file_path:
                continue
            
            # Evidence from changed functions
            changed_functions = file_data.get("changed_functions", []) or []
            for fn in changed_functions:
                fn_data = self._as_dict(fn)
                name = str(fn_data.get("name", "")).strip()
                if name:
                    evidence.append(Evidence(
                        type="function",
                        value=name,
                        source=file_path
                    ))
            
            # Evidence from keyword signals
            keyword_signals = file_data.get("keyword_signals", []) or []
            for signal in keyword_signals:
                signal_data = self._as_dict(signal)
                keyword = str(signal_data.get("keyword", "")).strip()
                category = str(signal_data.get("category", "")).strip()
                if keyword:
                    evidence.append(Evidence(
                        type="signal",
                        value=f"{category}:{keyword}",
                        source=file_path
                    ))
            
            # Evidence from risk events (flows)
            flows = file_data.get("flows", []) or []
            for flow in flows:
                flow_str = self._enum_or_string(flow)
                if flow_str:
                    evidence.append(Evidence(
                        type="flow",
                        value=flow_str,
                        source=file_path
                    ))
        
        return evidence

    def _collect_changed_symbols(self, enriched_files: list[dict]) -> list[str]:
        """Collect fully qualified changed symbols (Class.method format)."""
        symbols: set[str] = set()
        
        for file_data in enriched_files:
            file_path = str(file_data.get("file_path", ""))
            changed_functions = file_data.get("changed_functions", []) or []
            
            for fn in changed_functions:
                fn_data = self._as_dict(fn)
                name = str(fn_data.get("name", "")).strip()
                if name:
                    # Include file context for disambiguation
                    symbol = f"{file_path}:{name}"
                    symbols.add(symbol)
        
        return sorted(symbols)

    def _collect_changed_lines(self, enriched_files: list[dict]) -> list[str]:
        """Collect the most important changed lines (10-20 lines max)."""
        lines: list[str] = []
        
        for file_data in enriched_files:
            hunks = file_data.get("hunks", []) or []
            for hunk in hunks:
                hunk_data = self._as_dict(hunk)
                for raw_line in hunk_data.get("lines", []) or []:
                    line_data = self._as_dict(raw_line)
                    line_type = str(line_data.get("line_type", ""))
                    content = str(line_data.get("content", "")).strip()
                    
                    if line_type in ("added", "removed") and content:
                        # Filter out trivial changes
                        if len(content) > 3 and not content.startswith("#"):
                            lines.append(f"{line_type}: {content}")
                            
                            if len(lines) >= 20:
                                return lines
        
        return lines

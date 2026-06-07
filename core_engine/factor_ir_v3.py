"""
Factor IR v3 — Canonical reasoning intermediate representation for the LLM.

Replaces the old "unknowns" dump zone with structured CausalHypothesis
objects attached to causal graph edges. Each hypothesis is a structured
inference about what might happen downstream from a changed symbol.

Architecture:
  core_context       → flows, entry_points (deterministic)
  change_graph       → symbol-level change nodes (deterministic)
  behavior_diff      → before/after per function (deterministic)
  causal_hypotheses  → structured hypotheses on causal edges (probabilistic)
  system_regions     → domains touched (deterministic)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core_engine.behavior_diff_builder import BehaviorDiff


@dataclass
class CausalHypothesis:
    """
    A structured hypothesis about production impact attached to a causal edge.

    Replaces the old free-text "unknowns" bucket with typed, scored,
    edge-attached inferences.
    """
    from_symbol: str
    to_symbol: str
    edge_type: str  # data_flow | control_flow | shared_state | async_event | db_dependency
    hypothesis: str
    confidence: float  # 0.0 - 1.0, propagated from causal edge
    propagation_path: list[str] = field(default_factory=list)
    failure_class: str = ""  # e.g. "null_propagation", "stale_cache"
    evidence: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "from": self.from_symbol,
            "to": self.to_symbol,
            "edge_type": self.edge_type,
            "hypothesis": self.hypothesis,
            "confidence": round(self.confidence, 3),
            "propagation_path": self.propagation_path,
            "failure_class": self.failure_class,
            "evidence": self.evidence,
        }


class FactorIRv3Builder:
    """
    Build the canonical Factor IR v3 payload.

    Single reasoning spine:
      core_context + change_graph + behavior_diff + causal_hypotheses + system_regions
    """

    DOMAIN_REGIONS = (
        "checkout",
        "discount",
        "payment",
        "billing",
        "invoice",
        "auth",
        "authentication",
        "subscription",
        "order",
        "tax",
    )

    # Map edge types to hypothesis templates
    HYPOTHESIS_TEMPLATES: dict[str, list[dict[str, Any]]] = {
        "data_flow": [
            {
                "hypothesis": "changed {from_symbol} output flows to {to_symbol} — may propagate incorrect data",
                "failure_class": "null_propagation",
            },
            {
                "hypothesis": "{to_symbol} depends on {from_symbol} — behavior change may cause unexpected results in {to_symbol}",
                "failure_class": "",
            },
        ],
        "control_flow": [
            {
                "hypothesis": "{from_symbol} controls execution of {to_symbol} — changed logic may bypass or redirect {to_symbol}",
                "failure_class": "logic_negation_flip",
            },
        ],
        "shared_state": [
            {
                "hypothesis": "{from_symbol} and {to_symbol} share state — change in {from_symbol} may cause inconsistent state in {to_symbol}",
                "failure_class": "state_inconsistency",
            },
            {
                "hypothesis": "shared state between {from_symbol} and {to_symbol} may cause partial update drift",
                "failure_class": "partial_update_drift",
            },
        ],
        "async_event": [
            {
                "hypothesis": "{from_symbol} emits event consumed by {to_symbol} — payload changes may cause silent drops in {to_symbol}",
                "failure_class": "async_event_mismatch",
            },
        ],
        "db_dependency": [
            {
                "hypothesis": "{from_symbol} and {to_symbol} access same DB collection — schema or query changes in {from_symbol} may affect {to_symbol}",
                "failure_class": "data_validation_removed",
            },
            {
                "hypothesis": "DB write in {from_symbol} cached/read in {to_symbol} — missing invalidation causes stale data in {to_symbol}",
                "failure_class": "stale_cache",
            },
        ],
    }

    def build(
        self,
        enriched_files: list[dict],
        behavior_diffs: list[BehaviorDiff],
        entry_points_affected: list[Any] | None = None,
        risk_patterns: list[Any] | None = None,
    ) -> dict[str, Any]:
        behavior_diff = [self._serialize_behavior_diff(item) for item in behavior_diffs]
        change_graph = self._build_change_graph(enriched_files, behavior_diffs)

        # Build structured causal hypotheses (replaces old unknowns bucket)
        causal_hypotheses = self._build_causal_hypotheses(
            enriched_files=enriched_files,
            behavior_diffs=behavior_diffs,
            risk_patterns=risk_patterns or [],
        )

        return {
            "core_context": {
                "flows": self._collect_flows(enriched_files),
                "entry_points": self._collect_entry_points(entry_points_affected or []),
            },
            "change_graph": change_graph,
            "behavior_diff": behavior_diff,
            "causal_hypotheses": causal_hypotheses,
            "system_regions": self._collect_system_regions(enriched_files),
        }

    def _build_change_graph(
        self,
        enriched_files: list[dict],
        behavior_diffs: list[BehaviorDiff],
    ) -> list[dict[str, str]]:
        diff_symbols = {item.symbol for item in behavior_diffs}
        nodes: list[dict[str, str]] = []
        seen: set[tuple[str, str, str]] = set()

        for file_data in enriched_files:
            file_path = str(file_data.get("file_path", "")).strip()
            if not file_path or self._is_test_file(file_path):
                continue

            for fn in file_data.get("changed_functions", []) or []:
                fn_data = self._as_dict(fn)
                name = str(fn_data.get("name", "")).strip()
                change_type = str(fn_data.get("change_type", "modified")).strip()
                if not name or not self._is_execution_critical(name, file_path):
                    continue

                symbol = name.split(".")[-1] if "." in name else name
                if diff_symbols and symbol not in diff_symbols:
                    continue

                key = (symbol, file_path, change_type)
                if key in seen:
                    continue
                seen.add(key)
                nodes.append(
                    {
                        "symbol": symbol,
                        "file": file_path,
                        "change_type": change_type,
                    }
                )

        if not nodes and behavior_diffs:
            for item in behavior_diffs:
                nodes.append(
                    {
                        "symbol": item.symbol,
                        "file": "",
                        "change_type": "modified",
                    }
                )

        return nodes[:20]

    def _build_causal_hypotheses(
        self,
        enriched_files: list[dict],
        behavior_diffs: list[BehaviorDiff],
        risk_patterns: list[Any],
    ) -> list[dict[str, Any]]:
        """
        Build structured causal hypotheses instead of raw text unknowns.

        Each hypothesis is attached to a specific causal relationship between
        symbols, with a confidence score and a failure class hypothesis.
        """
        hypotheses: list[CausalHypothesis] = []
        changed_symbols = {item.symbol for item in behavior_diffs}
        confirmed_themes = " ".join(
            f"{item.before} {item.after}".lower() for item in behavior_diffs
        )

        # 1. Build hypotheses from causal graph inference using enriched files
        #    We don't have the full causal graph here, but we can infer likely
        #    causal relationships from imports, shared state patterns, and async events
        inferred_edges: list[dict[str, Any]] = []

        for file_data in enriched_files:
            file_path = str(file_data.get("file_path", "")).lower()
            hunks = file_data.get("hunks", []) or []
            changed_functions = file_data.get("changed_functions", []) or []
            hunk_lines = self._collect_hunk_contents(hunks)

            file_symbols = set()
            for fn in changed_functions:
                fn_data = self._as_dict(fn)
                name = str(fn_data.get("name", "")).strip()
                if name:
                    symbol = name.split(".")[-1] if "." in name else name
                    file_symbols.add(symbol)

            if not file_symbols:
                continue

            # Look for call relationships in hunk lines
            for symbol in file_symbols:
                for line in hunk_lines:
                    # Detect function calls
                    calls = self._find_calls(line)
                    for called in calls:
                        if called != symbol and called not in ("self", "cls", "if", "for", "while"):
                            inferred_edges.append({
                                "from": symbol,
                                "to": called,
                                "edge_type": "data_flow",
                                "evidence": f"{symbol} calls {called} in {file_path}",
                                "file_path": file_path,
                            })

                    # Detect shared state patterns
                    if any(p in line for p in ("cache.", "redis.", "session.", "config.")):
                        inferred_edges.append({
                            "from": symbol,
                            "to": f"state:{symbol}",
                            "edge_type": "shared_state",
                            "evidence": f"{symbol} accesses shared state in {file_path}",
                            "file_path": file_path,
                        })

                    # Detect async event patterns
                    if any(p in line for p in ("queue.", "publish(", "emit(", "dispatch(")):
                        inferred_edges.append({
                            "from": symbol,
                            "to": f"event:{symbol}",
                            "edge_type": "async_event",
                            "evidence": f"{symbol} emits async event in {file_path}",
                            "file_path": file_path,
                        })

                    # Detect DB dependency patterns
                    if any(p in line for p in (".save(", ".update(", ".insert(", ".delete(", "db.", "query(")):
                        inferred_edges.append({
                            "from": symbol,
                            "to": f"db:{symbol}",
                            "edge_type": "db_dependency",
                            "evidence": f"{symbol} accesses database in {file_path}",
                            "file_path": file_path,
                        })

        # 2. Generate hypothesis for each inferred edge from changed symbols
        for edge in inferred_edges:
            from_sym = edge["from"]
            if from_sym not in changed_symbols:
                continue

            to_sym = edge["to"]
            edge_type = edge["edge_type"]
            evidence_text = edge.get("evidence", "")

            templates = self.HYPOTHESIS_TEMPLATES.get(edge_type, [])
            for tpl in templates:
                hypothesis_text = tpl["hypothesis"].format(
                    from_symbol=from_sym,
                    to_symbol=to_sym,
                )
                failure_class = tpl["failure_class"]

                # Confidence: starts at 0.5 for inferred edges, decays if unconfirmed
                base_confidence = 0.5
                if to_sym.startswith("state:") or to_sym.startswith("event:") or to_sym.startswith("db:"):
                    base_confidence = 0.4  # indirect targets are less certain

                hypothesis = CausalHypothesis(
                    from_symbol=from_sym,
                    to_symbol=to_sym,
                    edge_type=edge_type,
                    hypothesis=hypothesis_text,
                    confidence=base_confidence,
                    propagation_path=[from_sym, to_sym],
                    failure_class=failure_class,
                    evidence=evidence_text,
                )
                hypotheses.append(hypothesis)

        # 3. Generate hypotheses from risk patterns that don't have confirmed symbols
        for risk in risk_patterns:
            risk_data = self._as_dict(risk)
            event_type = self._enum_or_string(risk_data.get("type"))
            function = str(risk_data.get("function", "")).strip()
            file_path = str(risk_data.get("file_path", "")).strip()
            reason = str(risk_data.get("reason", "")).strip()

            symbol = function.split(".")[-1] if function else ""
            if symbol and symbol in changed_symbols:
                continue

            theme = event_type.lower().replace("_", " ")
            if theme and theme in confirmed_themes:
                continue

            # Build a structured hypothesis from the risk pattern
            label = symbol or file_path.split("/")[-1] or "changed code"
            hypothesis_text = ""
            failure_class = ""

            if event_type == "VALIDATION_REMOVED":
                hypothesis_text = f"validation may have been removed in {label} — data could bypass guard and reach downstream consumers"
                failure_class = "data_validation_removed"
            elif event_type in ("AUTH_BYPASS", "PERMISSION_REMOVED"):
                hypothesis_text = f"auth/permission check in {label} may be weakened or removed — unauthorized access possible"
                failure_class = "auth_bypass_chain"
            elif event_type == "TAX_CALCULATION_CHANGE":
                hypothesis_text = f"tax logic in {label} changed — downstream invoice/billing totals may be incorrect"
                failure_class = "tax_billing_mismatch"
            elif event_type == "FINANCIAL_LOGIC_CHANGE":
                hypothesis_text = f"financial logic in {label} changed — payment outcomes may diverge from expected"
                failure_class = "double_charge_double_write"
            elif event_type == "STATE_INCONSISTENCY":
                hypothesis_text = f"state transition in {label} changed — downstream consumers may see invalid states"
                failure_class = "state_inconsistency"
            elif event_type == "SCHEMA_MIGRATION":
                hypothesis_text = f"schema migration in {label} — deployment may fail or leave schema partially applied"
                failure_class = "partial_update_drift"
            elif reason:
                hypothesis_text = f"{reason} in {label} — unconfirmed hypothesis with potential downstream impact"
            else:
                continue

            hypotheses.append(CausalHypothesis(
                from_symbol=label,
                to_symbol="downstream",
                edge_type="data_flow",
                hypothesis=hypothesis_text,
                confidence=0.35,  # Lower confidence for unconfirmed risk patterns
                propagation_path=[label, "downstream"],
                failure_class=failure_class,
                evidence=reason or event_type,
            ))

        # 4. Deduplicate by (from, to, hypothesis)
        hypotheses = self._dedupe_hypotheses(hypotheses)

        # Sort by confidence descending, return top 12
        hypotheses.sort(key=lambda h: -h.confidence)
        return [h.to_dict() for h in hypotheses[:12]]

    def _dedupe_hypotheses(self, hypotheses: list[CausalHypothesis]) -> list[CausalHypothesis]:
        """Remove duplicate hypotheses by (from, to, hypothesis)."""
        seen: set[tuple[str, str, str]] = set()
        unique: list[CausalHypothesis] = []
        for h in hypotheses:
            key = (h.from_symbol, h.to_symbol, h.hypothesis[:80])
            if key in seen:
                continue
            seen.add(key)
            unique.append(h)
        return unique

    def _find_calls(self, line: str) -> list[str]:
        """Find function call targets in a line of code."""
        import re
        calls = re.findall(r'(?:self\.|\.)?([a-zA-Z_][a-zA-Z0-9_]*)\s*\(', line)
        return [c for c in calls if c not in ("if", "for", "while", "with", "return", "raise", "import", "print", "len", "int", "str", "float", "list", "dict", "set", "type", "isinstance", "hasattr", "getattr", "setattr", "super", "classmethod", "staticmethod")]

    def _collect_hunk_contents(self, hunks: list[Any]) -> list[str]:
        """Extract hunk line contents as plain strings."""
        lines: list[str] = []
        for hunk in hunks:
            hunk_data = self._as_dict(hunk)
            for raw_line in hunk_data.get("lines", []) or []:
                line_data = self._as_dict(raw_line)
                content = str(line_data.get("content", "")).strip()
                if content and not content.startswith("#"):
                    lines.append(content)
        return lines

    def _collect_system_regions(self, enriched_files: list[dict]) -> list[str]:
        regions: set[str] = set()
        for file_data in enriched_files:
            file_path = str(file_data.get("file_path", "")).lower()
            for region in self.DOMAIN_REGIONS:
                if region in file_path:
                    regions.add(region)
            for flow in file_data.get("flows", []) or []:
                flow_text = self._enum_or_string(flow).lower()
                for region in self.DOMAIN_REGIONS:
                    if region in flow_text:
                        regions.add(region)
        return sorted(regions)

    def _collect_flows(self, enriched_files: list[dict]) -> list[str]:
        values: set[str] = set()
        for file_data in enriched_files:
            for flow in file_data.get("flows", []) or []:
                flow_text = self._enum_or_string(flow)
                if flow_text:
                    values.add(flow_text)
        return sorted(values)

    def _collect_entry_points(self, entry_points_affected: list[Any]) -> list[str]:
        routes: set[str] = set()
        for ep in entry_points_affected:
            ep_data = self._as_dict(ep)
            route = str(ep_data.get("route", "")).strip()
            function = str(ep_data.get("function", "")).strip()
            if route:
                routes.add(route)
            elif function:
                routes.add(function)
        return sorted(routes)

    def _serialize_behavior_diff(self, item: BehaviorDiff) -> dict[str, str]:
        return {
            "symbol": item.symbol,
            "before": item.before,
            "after": item.after,
        }

    def _is_execution_critical(self, name: str, file_path: str) -> bool:
        lowered = name.lower()
        path_lower = file_path.lower()

        if self._is_test_file(file_path):
            return False
        if lowered.startswith("test") or ".test" in lowered:
            return False

        helper_prefixes = ("_build_", "_from_", "_to_", "_parse_", "_serialize_", "_deserialize_")
        base_name = lowered.split(".")[-1]
        if any(base_name.startswith(prefix) for prefix in helper_prefixes):
            return any(marker in lowered or marker in path_lower for marker in self.DOMAIN_REGIONS)

        utility_markers = ("util", "helper", "fixture", "factory", "mock", "stub")
        if any(marker in lowered for marker in utility_markers):
            return False

        if any(marker in lowered or marker in path_lower for marker in self.DOMAIN_REGIONS):
            return True

        if "." in name:
            owner = lowered.split(".")[0]
            if any(token in owner for token in ("service", "order", "checkout", "invoice")):
                return True

        return True

    def _is_test_file(self, file_path: str) -> bool:
        lowered = file_path.lower()
        return any(marker in lowered for marker in ("/tests/", "/test/", "/fixtures/", "/mocks/"))

    def _dedupe(self, values: list[str]) -> list[str]:
        seen: set[str] = set()
        unique: list[str] = []
        for value in values:
            key = value.lower()
            if key in seen:
                continue
            seen.add(key)
            unique.append(value)
        return unique

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


def build_factor_ir_v3(
    enriched_files: list[dict],
    behavior_diffs: list[BehaviorDiff],
    entry_points_affected: list[Any] | None = None,
    risk_patterns: list[Any] | None = None,
) -> dict[str, Any]:
    return FactorIRv3Builder().build(
        enriched_files=enriched_files,
        behavior_diffs=behavior_diffs,
        entry_points_affected=entry_points_affected,
        risk_patterns=risk_patterns,
    )
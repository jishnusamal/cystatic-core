"""
System-level Behavior Delta — "behavior_delta_system_level"

This is what engineers actually reason about:
  - "tax logic now depends on breakdown instead of rate"
  - "invoice total now aggregates multiple sources"

Not just "function X changed" — but the SYSTEM-LEVEL semantic shift.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SystemBehaviorDelta:
    """A system-level behavior change description."""
    description: str
    system_regions: list[str] = field(default_factory=list)
    involved_symbols: list[str] = field(default_factory=list)
    change_category: str = ""  # dependency_shift | aggregation_change | logic_inversion | data_flow_change
    confidence: float = 0.7
    severity: str = "MEDIUM"  # CRITICAL | HIGH | MEDIUM | LOW | INFO
    causal_chain: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "description": self.description,
            "system_regions": self.system_regions,
            "involved_symbols": self.involved_symbols,
            "change_category": self.change_category,
            "confidence": round(self.confidence, 2),
            "severity": self.severity,
            "causal_chain": self.causal_chain,
        }


class SystemBehaviorDeltaBuilder:
    """
    Infers system-level behavior deltas from:
    - behavior_diffs (function-level before/after)
    - causal graph edges
    - risk patterns
    - enriched file data
    - failure template matches
    """

    # Maps function-level patterns to system-level deltas
    SYSTEM_DELTA_PATTERNS: list[dict[str, Any]] = [
        {
            "category": "dependency_shift",
            "description": "{symbol} now depends on {target} instead of {source}",
            "patterns": ["depends on", "instead of", "replaced with", "changed from", "switched to"],
            "severity": "HIGH",
        },
        {
            "category": "aggregation_change",
            "description": "{symbol} aggregates from {source} instead of {previous_source}",
            "patterns": ["sum(", "total", "aggregate", "collect", "combine", "merge"],
            "severity": "HIGH",
        },
        {
            "category": "logic_inversion",
            "description": "{symbol} logic inverted: {before} → {after}",
            "patterns": ["not ", "!=", "invert", "flip", "reverse"],
            "severity": "HIGH",
        },
        {
            "category": "data_flow_change",
            "description": "{symbol} output now flows to {target} instead of {previous_target}",
            "patterns": ["return", "yield", "emit", "send", "publish", "write"],
            "severity": "MEDIUM",
        },
        {
            "category": "validation_change",
            "description": "{symbol} validation was {'removed' if removed else 'added'}",
            "patterns": ["validate", "check", "assert", "raise", "guard"],
            "severity": "CRITICAL",
        },
        {
            "category": "state_transition_change",
            "description": "{symbol} state or status transition logic changed",
            "patterns": ["state", "status", "transition", "stage", "phase"],
            "severity": "HIGH",
        },
    ]

    def build(
        self,
        enriched_files: list[dict],
        behavior_diffs: list[Any],
        causal_graph: Any | None = None,
        failure_template_matches: list[dict] | None = None,
    ) -> list[SystemBehaviorDelta]:
        """Build system-level behavior deltas from multiple inputs."""
        deltas: list[SystemBehaviorDelta] = []

        # 1. From behavior diffs
        for diff in behavior_diffs:
            diff_data = self._as_dict(diff)
            symbol = str(diff_data.get("symbol", ""))
            before = str(diff_data.get("before", ""))
            after = str(diff_data.get("after", ""))

            if not symbol:
                continue

            # Check each system delta pattern
            for pattern_def in self.SYSTEM_DELTA_PATTERNS:
                if self._matches_pattern(before, after, pattern_def["patterns"]):
                    delta = self._build_delta(symbol, before, after, pattern_def)
                    if delta:
                        deltas.append(delta)
                    break  # Only the best matching pattern

        # 2. From failure template matches (if provided)
        if failure_template_matches:
            for match in failure_template_matches[:3]:  # top 3
                template_name = str(match.get("template_name", ""))
                description = str(match.get("description", ""))
                regions = match.get("matched_system_regions", [])
                confidence = float(match.get("confidence", 0.5))

                deltas.append(SystemBehaviorDelta(
                    description=f"Potential {template_name}: {description}",
                    system_regions=regions,
                    change_category="failure_template_match",
                    confidence=confidence * 0.8,  # downgrade template match vs direct evidence
                    severity=str(match.get("severity", "MEDIUM")),
                ))

        # 3. From causal graph (if provided) — detect data flow changes
        if causal_graph is not None:
            try:
                graph_data = causal_graph.to_dict() if hasattr(causal_graph, 'to_dict') else {}
                edges = graph_data.get("edges", [])
                # Look for symbols with multiple outgoing edges — potential flow changes
                edge_counts: dict[str, int] = {}
                for edge in edges:
                    from_sym = edge.get("from", "")
                    if from_sym:
                        edge_counts[from_sym] = edge_counts.get(from_sym, 0) + 1

                for symbol, count in edge_counts.items():
                    if count >= 3:
                        deltas.append(SystemBehaviorDelta(
                            description=f"{symbol} has {count} downstream dependencies — changes propagate broadly",
                            system_regions=["Core"],
                            involved_symbols=[symbol],
                            change_category="data_flow_change",
                            confidence=0.5,
                            severity="HIGH",
                            causal_chain=[f"{symbol} → {edge.get('to', '')}" for edge in edges if edge.get("from") == symbol][:3],
                        ))
            except Exception:
                pass  # Gracefully handle missing causal graph data

        # 4. Deduplicate by description
        return self._dedupe(deltas)[:10]

    def _matches_pattern(self, before: str, after: str, patterns: list[str]) -> bool:
        """Check if a before/after pair matches a set of patterns."""
        combined = f"{before} {after}".lower()
        for pattern in patterns:
            if pattern.lower() in combined:
                # Exclude trivial matches
                if pattern == "return" and len(combined) < 20:
                    continue
                return True
        # Check for semantic shifts
        if before and after and before != after:
            # Before had validation, after doesn't
            validation_markers = ("raise", "assert", "validate", "check")
            if any(m in before.lower() for m in validation_markers) and not any(m in after.lower() for m in validation_markers):
                return True
            # Before had auth, after doesn't
            auth_markers = ("authenticate", "authorize", "login_required", "permission")
            if any(m in before.lower() for m in auth_markers) and not any(m in after.lower() for m in auth_markers):
                return True
        return False

    def _build_delta(
        self,
        symbol: str,
        before: str,
        after: str,
        pattern_def: dict[str, Any],
    ) -> SystemBehaviorDelta | None:
        """Build a SystemBehaviorDelta from a matched pattern."""
        description = pattern_def["description"]
        # Fill in placeholders
        description = description.replace("{symbol}", symbol)
        description = description.replace("{before}", before[:80] if before else "?")
        description = description.replace("{after}", after[:80] if after else "?")
        description = description.replace("{target}", after.split(" ")[0] if after else "?")
        description = description.replace("{source}", before.split(" ")[0] if before else "?")
        description = description.replace("{previous_source}", before.split(" ")[0] if before else "?")
        description = description.replace("{previous_target}", before.split(" ")[0] if before else "?")

        # Infer system regions from symbol and context
        regions = self._infer_regions(symbol, before, after)

        return SystemBehaviorDelta(
            description=description,
            system_regions=regions,
            involved_symbols=[symbol],
            change_category=pattern_def["category"],
            confidence=0.7,
            severity=pattern_def["severity"],
            causal_chain=[f"{symbol}: {before[:60]} → {after[:60]}"],
        )

    def _infer_regions(self, symbol: str, before: str, after: str) -> list[str]:
        """Infer system regions from symbol name and context."""
        regions: set[str] = set()
        combined = f"{symbol} {before} {after}".lower()

        region_map = {
            "checkout": "Checkout",
            "payment": "Payment",
            "billing": "Billing",
            "invoice": "Invoice",
            "tax": "Tax",
            "auth": "Authentication",
            "order": "Order",
            "subscription": "Subscription",
            "discount": "Discount",
            "shipping": "Shipping",
            "notification": "Notification",
            "webhook": "Webhook",
            "cache": "Caching",
        }

        for keyword, region in region_map.items():
            if keyword in combined:
                regions.add(region)

        if not regions:
            regions.add("Core")

        return sorted(regions)

    def _dedupe(self, deltas: list[SystemBehaviorDelta]) -> list[SystemBehaviorDelta]:
        """Remove duplicate deltas by description."""
        seen: set[str] = set()
        unique: list[SystemBehaviorDelta] = []
        for delta in deltas:
            key = delta.description.lower()[:100]
            if key in seen:
                continue
            seen.add(key)
            unique.append(delta)
        return unique

    def _as_dict(self, value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        if hasattr(value, "model_dump"):
            return value.model_dump()
        return {}


def build_system_behavior_deltas(
    enriched_files: list[dict],
    behavior_diffs: list[Any],
    causal_graph: Any | None = None,
    failure_template_matches: list[dict] | None = None,
) -> list[SystemBehaviorDelta]:
    """Convenience function for building system behavior deltas."""
    return SystemBehaviorDeltaBuilder().build(
        enriched_files=enriched_files,
        behavior_diffs=behavior_diffs,
        causal_graph=causal_graph,
        failure_template_matches=failure_template_matches,
    )
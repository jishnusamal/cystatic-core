"""SharedExecutionPass — converts existing shared execution compiler output into Discovery objects.

Reuses existing compiler output:
- BehaviorModel.shared_executions: pre-computed shared execution data
  (symbols used by multiple behaviors, with used_by list)

The shared execution analysis already exists in behavior/compiler/passes/shared_execution/.
This pass only converts that output into Discovery objects — no duplicate traversal.
"""
from __future__ import annotations

from engine.operational.discovery.model import (
    Discovery,
    DiscoveryKind,
    DiscoverySupport,
    DiscoveryEvidence,
)
from engine.operational.discovery.passes.base import DiscoveryPassContext, DiscoveryCompilerPass


class SharedExecutionPass(DiscoveryCompilerPass):
    """Converts existing shared execution compiler output into Discovery objects.

    Emits discoveries like:
    - "CustomerWithMembers is reused by five REST endpoints."
    - "validate_discount() is shared by Checkout and AdminPanel behaviors."
    """

    @property
    def name(self) -> str:
        return "shared_execution"

    def run(self, context: DiscoveryPassContext) -> DiscoveryPassContext:
        """Emit shared execution discoveries from existing compiler output."""
        model = context.discovery_model
        if model is None:
            return context

        behavior = model.behavior
        if behavior is None:
            return context

        # Reuse the pre-computed shared_executions from the behavior model
        shared_executions = getattr(behavior, 'shared_executions', ())
        behaviors = getattr(behavior, 'behaviors', ())

        if not shared_executions:
            return context

        # Build a map: behavior_id -> behavior name/entry point
        behavior_names: dict[str, str] = {}
        for b in behaviors:
            name = getattr(b, 'name', '')
            if not name:
                entry = getattr(b, 'entry_point', '')
                name = entry.split('/')[-1] if '/' in entry else entry
            behavior_names[b.id] = name or b.id

        for se in shared_executions:
            symbol_id = getattr(se, 'symbol_id', '')
            used_by = getattr(se, 'used_by', ())
            if not symbol_id or len(used_by) < 2:
                continue

            name = self._derive_symbol_name(symbol_id)
            count = len(used_by)

            # Get behavior names for the used_by list
            behavior_labels = []
            for bid in used_by[:5]:
                label = behavior_names.get(bid, bid)
                behavior_labels.append(label)
            extra = f" and {count - 5} more" if count > 5 else ""

            statement = (
                f"{name} is reused by {count} "
                f"behavior{'s' if count != 1 else ''}"
                f"{': ' if behavior_labels else ''}"
                f"{', '.join(behavior_labels)}{extra}."
            )

            evidence_list = [
                DiscoveryEvidence(
                    source="behavior",
                    source_id=symbol_id,
                    description=f"Symbol '{name}' is shared by {count} behaviors",
                    evidence_ref=f"behavior://shared/{symbol_id}",
                ),
            ]
            for bid in used_by[:5]:
                label = behavior_names.get(bid, bid)
                evidence_list.append(
                    DiscoveryEvidence(
                        source="behavior",
                        source_id=bid,
                        description=f"Behavior: {label}",
                        evidence_ref=f"behavior://{bid}",
                    )
                )

            context.discoveries.append(Discovery(
                id=f"shared-execution://{symbol_id}",
                kind=DiscoveryKind.SHARED_EXECUTION,
                statement=statement,
                importance=min(0.4 + 0.1 * count, 0.95),
                support=DiscoverySupport(
                    shared_by_count=count,
                ),
                evidence=tuple(evidence_list),
                metadata={
                    "symbol_id": symbol_id,
                    "name": name,
                    "shared_by_count": count,
                    "used_by": list(used_by),
                },
            ))

        return context

    @staticmethod
    def _derive_symbol_name(symbol_id: str) -> str:
        """Derive a human-readable name from a symbol id."""
        if "://" in symbol_id:
            rest = symbol_id.split("://", 1)[1]
        else:
            rest = symbol_id
        name = rest.split("#")[-1].split("::")[-1]
        return name.replace("_", " ").title()
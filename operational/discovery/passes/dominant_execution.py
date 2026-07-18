"""DominantExecutionPass — identifies modified symbols with the greatest execution reach.

Reuses existing compiler outputs:
- DependencyModel.fan_in: per-symbol caller counts
- DependencyModel.fan_out: per-symbol callee counts
- BehaviorModel.reachable_units: execution units reachable from changed symbols
- BehaviorModel.execution_chains: ordered execution paths per behavior
- BehaviorModel.execution_depth: maximum execution depth
- BehaviorModel.shared_executions: symbols shared across behaviors

No duplicate graph traversal — all data is read from pre-computed models.
"""
from __future__ import annotations

from operational.discovery.model import (
    Discovery,
    DiscoveryKind,
    DiscoverySupport,
    DiscoveryEvidence,
)
from operational.discovery.passes.base import DiscoveryPassContext, DiscoveryCompilerPass


class DominantExecutionPass(DiscoveryCompilerPass):
    """Identifies the modified symbols with the greatest execution reach.

    Emits discoveries like:
    - "Checkout.confirm() reaches 315 execution units."
    - "CustomerRepository.load() is referenced by 39 upstream callers."
    - "The deepest execution path spans 33 calls."
    """

    @property
    def name(self) -> str:
        return "dominant_execution"

    def run(self, context: DiscoveryPassContext) -> DiscoveryPassContext:
        """Emit dominant execution discoveries from existing compiler outputs."""
        model = context.discovery_model
        if model is None:
            return context

        behavior = model.behavior
        change = model.change
        if behavior is None or change is None:
            return context

        # --- Discovery 1: Largest fan-in ---
        # Reuse DependencyModel.fan_in
        dependency = getattr(model, 'dependency', None)
        if dependency is not None:
            fan_in = getattr(dependency, 'fan_in', {})
            if fan_in:
                # Sort by fan-in descending, take top 3
                sorted_fan_in = sorted(fan_in.items(), key=lambda x: -x[1])
                for symbol_id, count in sorted_fan_in[:3]:
                    if count < 2:
                        continue
                    name = self._derive_symbol_name(symbol_id)
                    statement = (
                        f"{name} is referenced by {count} upstream "
                        f"caller{'s' if count != 1 else ''}."
                    )
                    context.discoveries.append(Discovery(
                        id=f"dominant-execution://fan-in/{symbol_id}",
                        kind=DiscoveryKind.FAN_IN,
                        statement=statement,
                        importance=min(0.3 + 0.05 * count, 0.95),
                        support=DiscoverySupport(fan_in=count),
                        evidence=(
                            DiscoveryEvidence(
                                source="operational",
                                source_id=symbol_id,
                                description=f"Symbol '{name}' has fan-in of {count}",
                                evidence_ref=f"operational://dependency/fan-in/{symbol_id}",
                            ),
                        ),
                        metadata={"symbol_id": symbol_id, "name": name, "fan_in": count},
                    ))

        # --- Discovery 2: Largest fan-out ---
        if dependency is not None:
            fan_out = getattr(dependency, 'fan_out', {})
            if fan_out:
                sorted_fan_out = sorted(fan_out.items(), key=lambda x: -x[1])
                for symbol_id, count in sorted_fan_out[:3]:
                    if count < 2:
                        continue
                    name = self._derive_symbol_name(symbol_id)
                    statement = (
                        f"{name} calls {count} downstream "
                        f"callee{'s' if count != 1 else ''}."
                    )
                    context.discoveries.append(Discovery(
                        id=f"dominant-execution://fan-out/{symbol_id}",
                        kind=DiscoveryKind.FAN_OUT,
                        statement=statement,
                        importance=min(0.3 + 0.05 * count, 0.95),
                        support=DiscoverySupport(fan_out=count),
                        evidence=(
                            DiscoveryEvidence(
                                source="operational",
                                source_id=symbol_id,
                                description=f"Symbol '{name}' has fan-out of {count}",
                                evidence_ref=f"operational://dependency/fan-out/{symbol_id}",
                            ),
                        ),
                        metadata={"symbol_id": symbol_id, "name": name, "fan_out": count},
                    ))

        # --- Discovery 3: Largest execution reach ---
        # Count reachable units per behavior
        reachable_units = getattr(behavior, 'reachable_units', ())
        behaviors = getattr(behavior, 'behaviors', ())
        execution_chains = getattr(behavior, 'execution_chains', ())

        if reachable_units and behaviors:
            # Group reachable units by behavior
            behavior_unit_counts: dict[str, int] = {}
            for unit in reachable_units:
                uid = getattr(unit, 'id', '')
                if '://' in uid:
                    bid = uid.split('://')[1].split('#')[0]
                else:
                    continue
                if bid not in behavior_unit_counts:
                    behavior_unit_counts[bid] = 0
                behavior_unit_counts[bid] += 1

            # Find the behavior with the most reachable units
            if behavior_unit_counts:
                top_bid = max(behavior_unit_counts, key=behavior_unit_counts.get)
                top_count = behavior_unit_counts[top_bid]

                # Find the behavior name
                top_behavior = None
                for b in behaviors:
                    if b.id == top_bid:
                        top_behavior = b
                        break

                if top_behavior is not None:
                    name = self._derive_behavior_name(top_behavior)
                    statement = (
                        f"{name} reaches {top_count} execution "
                        f"unit{'s' if top_count != 1 else ''}."
                    )
                    context.discoveries.append(Discovery(
                        id=f"dominant-execution://reach/{top_bid}",
                        kind=DiscoveryKind.DOMINANT_EXECUTION,
                        statement=statement,
                        importance=min(0.4 + 0.02 * top_count, 0.95),
                        support=DiscoverySupport(execution_reach=top_count),
                        evidence=(
                            DiscoveryEvidence(
                                source="behavior",
                                source_id=top_bid,
                                description=f"Behavior '{name}' reaches {top_count} execution units",
                                evidence_ref=f"behavior://reachable/{top_bid}",
                            ),
                        ),
                        metadata={"behavior_id": top_bid, "name": name, "reachable_count": top_count},
                    ))

        # --- Discovery 4: Deepest execution path ---
        execution_depth = getattr(behavior, 'execution_depth', 0)
        if execution_depth > 0:
            # Find which chain has the most units
            max_units = 0
            max_chain_bid = ''
            for chain in execution_chains:
                units = getattr(chain, 'units', ())
                if len(units) > max_units:
                    max_units = len(units)
                    max_chain_bid = getattr(chain, 'behavior_id', '')

            if max_units > 0:
                # Find the behavior name
                chain_behavior = None
                for b in behaviors:
                    if b.id == max_chain_bid:
                        chain_behavior = b
                        break

                behavior_label = self._derive_behavior_name(chain_behavior) if chain_behavior else max_chain_bid
                statement = (
                    f"The deepest execution path spans {max_units} "
                    f"call{'s' if max_units != 1 else ''} "
                    f"({behavior_label})."
                )
                context.discoveries.append(Discovery(
                    id=f"dominant-execution://depth/{max_chain_bid}",
                    kind=DiscoveryKind.EXECUTION_DEPTH,
                    statement=statement,
                    importance=0.6,
                    support=DiscoverySupport(
                        execution_reach=max_units,
                        propagation_depth=execution_depth,
                    ),
                    evidence=(
                        DiscoveryEvidence(
                            source="behavior",
                            source_id=max_chain_bid,
                            description=f"Execution depth of {execution_depth} with {max_units} units",
                            evidence_ref=f"behavior://depth/{max_chain_bid}",
                        ),
                    ),
                    metadata={
                        "behavior_id": max_chain_bid,
                        "execution_depth": execution_depth,
                        "max_units": max_units,
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

    @staticmethod
    def _derive_behavior_name(behavior) -> str:
        """Derive a human-readable name from a behavior."""
        name = getattr(behavior, 'name', '')
        if name:
            return name
        entry = getattr(behavior, 'entry_point', '')
        if entry:
            return entry.split('/')[-1] if '/' in entry else entry
        return getattr(behavior, 'id', 'unknown')
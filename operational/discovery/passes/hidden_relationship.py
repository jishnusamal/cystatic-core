"""HiddenRelationshipPass — reveals non-obvious relationships from the change.

Reuses existing compiler outputs:
- BehaviorModel.reachable_units: execution units reachable from changed symbols
- BehaviorModel.execution_chains: ordered execution paths per behavior
- BehaviorModel.entry_points: where execution begins
- BehaviorModel.behaviors: affected behavioral units
- DependencyModel.fan_in: per-symbol caller counts
- DependencyModel.fan_out: per-symbol callee counts

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


class HiddenRelationshipPass(DiscoveryCompilerPass):
    """Reveals relationships that are not obvious from reading the PR.

    Emits discoveries like:
    - "CustomerWithMembers is reachable from five REST endpoints."
    - "BillingService is reached indirectly through Checkout.confirm()."
    """

    @property
    def name(self) -> str:
        return "hidden_relationship"

    def run(self, context: DiscoveryPassContext) -> DiscoveryPassContext:
        """Emit hidden relationship discoveries from existing compiler outputs."""
        model = context.discovery_model
        if model is None:
            return context

        behavior = model.behavior
        if behavior is None:
            return context

        # --- Discovery 1: Entry point reachability ---
        # For each behavior, show how many entry points reach it
        entry_points = getattr(behavior, 'entry_points', ())
        behaviors = getattr(behavior, 'behaviors', ())
        reachable_units = getattr(behavior, 'reachable_units', ())
        execution_chains = getattr(behavior, 'execution_chains', ())

        # Build a map: behavior_id -> list of entry point routes
        behavior_to_entry_points: dict[str, list[str]] = {}
        for ep in entry_points:
            bid = getattr(ep, 'behavior_id', None)
            route = getattr(ep, 'route', '')
            if bid and route:
                if bid not in behavior_to_entry_points:
                    behavior_to_entry_points[bid] = []
                behavior_to_entry_points[bid].append(route)

        # For each behavior with multiple entry points, emit a discovery
        for b in behaviors:
            bid = b.id
            routes = behavior_to_entry_points.get(bid, [])
            if len(routes) >= 2:
                name = self._derive_name(b)
                route_list = ", ".join(routes[:5])
                extra = f" and {len(routes) - 5} more" if len(routes) > 5 else ""
                statement = (
                    f"{name} is reachable from {len(routes)} "
                    f"REST endpoint{'s' if len(routes) != 1 else ''}: "
                    f"{route_list}{extra}."
                )
                evidence_list = [
                    DiscoveryEvidence(
                        source="behavior",
                        source_id=bid,
                        description=f"Behavior '{name}' has {len(routes)} entry point(s)",
                        evidence_ref=f"behavior://{bid}",
                    )
                ]
                for r in routes[:5]:
                    evidence_list.append(
                        DiscoveryEvidence(
                            source="behavior",
                            source_id=f"entry://{bid}",
                            description=f"Entry point: {r}",
                            evidence_ref=f"behavior://entry/{bid}",
                        )
                    )
                context.discoveries.append(Discovery(
                    id=f"hidden-relationship://reachable/{bid}",
                    kind=DiscoveryKind.HIDDEN_RELATIONSHIP,
                    statement=statement,
                    importance=min(0.5 + 0.1 * len(routes), 0.95),
                    support=DiscoverySupport(
                        execution_reach=len(routes),
                    ),
                    evidence=tuple(evidence_list),
                    metadata={"behavior_id": bid, "name": name, "entry_point_count": len(routes)},
                ))

        # --- Discovery 2: Indirect reachability ---
        # For each execution chain, show the path from entry to changed symbols
        for chain in execution_chains:
            units = getattr(chain, 'units', ())
            if len(units) < 2:
                continue
            bid = getattr(chain, 'behavior_id', '')
            if not bid:
                continue

            # Find the behavior for this chain
            behavior_obj = None
            for b in behaviors:
                if b.id == bid:
                    behavior_obj = b
                    break
            if behavior_obj is None:
                continue

            # Get the entry point route
            entry_route = getattr(behavior_obj, 'entry_point', '')
            entry_name = entry_route.split('/')[-1] if '/' in entry_route else entry_route

            # Find the deepest changed symbol in the chain
            changed_ids = set(getattr(behavior_obj, 'changed_symbol_ids', ()))
            deepest_changed = None
            deepest_order = -1
            for unit in units:
                if unit.symbol_id in changed_ids and unit.order > deepest_order:
                    deepest_changed = unit
                    deepest_order = unit.order

            if deepest_changed is None:
                continue

            # Find the terminal point (last unit)
            terminal_unit = units[-1] if units else None
            if terminal_unit is None:
                continue

            # Only emit if the changed symbol is not the entry point itself
            root_id = getattr(behavior_obj, 'root_symbol_id', '')
            if deepest_changed.symbol_id == root_id:
                continue

            changed_name = self._derive_unit_name(deepest_changed.symbol_id)
            terminal_name = self._derive_unit_name(terminal_unit.symbol_id)
            path_length = len(units)

            statement = (
                f"{changed_name} is reached indirectly through "
                f"{entry_name} ({path_length} execution unit{'s' if path_length != 1 else ''} "
                f"from entry to terminal at {terminal_name})."
            )

            context.discoveries.append(Discovery(
                id=f"hidden-relationship://indirect/{bid}",
                kind=DiscoveryKind.HIDDEN_RELATIONSHIP,
                statement=statement,
                importance=0.7,
                support=DiscoverySupport(
                    execution_reach=path_length,
                    propagation_depth=path_length,
                ),
                evidence=(
                    DiscoveryEvidence(
                        source="behavior",
                        source_id=bid,
                        description=f"Execution chain for '{entry_name}' has {path_length} units",
                        evidence_ref=f"behavior://chain/{bid}",
                    ),
                    DiscoveryEvidence(
                        source="behavior",
                        source_id=deepest_changed.symbol_id,
                        description=f"Changed symbol '{changed_name}' at depth {deepest_order}",
                        evidence_ref=f"behavior://reachable/{bid}#{deepest_changed.symbol_id}",
                    ),
                ),
                metadata={
                    "behavior_id": bid,
                    "entry_point": entry_route,
                    "changed_symbol": deepest_changed.symbol_id,
                    "path_length": path_length,
                },
            ))

        return context

    @staticmethod
    def _derive_name(behavior) -> str:
        """Derive a human-readable name from a behavior."""
        name = getattr(behavior, 'name', '')
        if name:
            return name
        entry = getattr(behavior, 'entry_point', '')
        if entry:
            return entry.split('/')[-1] if '/' in entry else entry
        return getattr(behavior, 'id', 'unknown')

    @staticmethod
    def _derive_unit_name(symbol_id: str) -> str:
        """Derive a human-readable name from a symbol id."""
        if "://" in symbol_id:
            rest = symbol_id.split("://", 1)[1]
        else:
            rest = symbol_id
        name = rest.split("#")[-1].split("::")[-1]
        return name.replace("_", " ").title()
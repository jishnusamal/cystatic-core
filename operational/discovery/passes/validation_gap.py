"""ValidationGapPass — expresses missing validation in terms of execution paths.

Reuses existing compiler outputs:
- ValidationModel: test coverage evidence (unit_tests, integration_tests, e2e_tests)
- BehaviorModel.execution_chains: ordered execution paths per behavior
- BehaviorModel.behaviors: affected behavioral units
- DependencyModel.fan_out: per-symbol callee counts (for weighting gaps)

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


class ValidationGapPass(DiscoveryCompilerPass):
    """Expresses missing validation in terms of execution paths.

    Emits discoveries like:
    - "The Checkout → Billing execution path has no end-to-end validation."
    - "CustomerRepository.load() (fan-out=12) has no integration test coverage."
    """

    @property
    def name(self) -> str:
        return "validation_gap"

    def run(self, context: DiscoveryPassContext) -> DiscoveryPassContext:
        """Emit validation gap discoveries from existing compiler outputs."""
        model = context.discovery_model
        if model is None:
            return context

        behavior = model.behavior
        validation = getattr(model, 'validation', None)
        dependency = getattr(model, 'dependency', None)

        if behavior is None:
            return context

        behaviors = getattr(behavior, 'behaviors', ())
        execution_chains = getattr(behavior, 'execution_chains', ())

        # Get test coverage counts
        unit_count = 0
        integration_count = 0
        e2e_count = 0
        if validation is not None:
            unit_tests = getattr(validation, 'unit_tests', ())
            integration_tests = getattr(validation, 'integration_tests', ())
            e2e_tests = getattr(validation, 'e2e_tests', ())
            unit_count = len(unit_tests)
            integration_count = len(integration_tests)
            e2e_count = len(e2e_tests)

        total_tests = unit_count + integration_count + e2e_count

        # --- Discovery 1: Execution paths without end-to-end validation ---
        # For each behavior with an execution chain, check if there's e2e coverage
        for chain in execution_chains:
            units = getattr(chain, 'units', ())
            if len(units) < 2:
                continue
            bid = getattr(chain, 'behavior_id', '')
            if not bid:
                continue

            # Find the behavior
            behavior_obj = None
            for b in behaviors:
                if b.id == bid:
                    behavior_obj = b
                    break
            if behavior_obj is None:
                continue

            entry_route = getattr(behavior_obj, 'entry_point', '')
            entry_name = entry_route.split('/')[-1] if '/' in entry_route else entry_route

            # Find the terminal unit name
            terminal_unit = units[-1]
            terminal_name = self._derive_unit_name(terminal_unit.symbol_id)

            # Check if this behavior has e2e coverage
            has_e2e = e2e_count > 0
            has_integration = integration_count > 0

            if not has_e2e and len(units) >= 3:
                statement = (
                    f"The {entry_name} → {terminal_name} execution path "
                    f"({len(units)} unit{'s' if len(units) != 1 else ''}) "
                    f"has no end-to-end validation."
                )
                context.discoveries.append(Discovery(
                    id=f"validation-gap://e2e/{bid}",
                    kind=DiscoveryKind.VALIDATION_GAP,
                    statement=statement,
                    importance=0.75,
                    support=DiscoverySupport(
                        execution_reach=len(units),
                        validation_gaps=1,
                    ),
                    evidence=(
                        DiscoveryEvidence(
                            source="behavior",
                            source_id=bid,
                            description=f"Execution chain '{entry_name}' has {len(units)} units",
                            evidence_ref=f"behavior://chain/{bid}",
                        ),
                        DiscoveryEvidence(
                            source="operational",
                            source_id="validation",
                            description=f"No e2e tests found (unit={unit_count}, integration={integration_count})",
                            evidence_ref="operational://validation",
                        ),
                    ),
                    metadata={
                        "behavior_id": bid,
                        "entry_point": entry_route,
                        "terminal": terminal_unit.symbol_id,
                        "path_length": len(units),
                        "has_e2e": has_e2e,
                        "has_integration": has_integration,
                    },
                ))

        # --- Discovery 2: High fan-out symbols without integration tests ---
        if dependency is not None:
            fan_out = getattr(dependency, 'fan_out', {})
            if fan_out and integration_count == 0:
                # Find symbols with high fan-out
                sorted_fan_out = sorted(fan_out.items(), key=lambda x: -x[1])
                for symbol_id, count in sorted_fan_out[:3]:
                    if count < 3:
                        continue
                    name = self._derive_symbol_name(symbol_id)
                    statement = (
                        f"{name} (fan-out={count}) has no integration test coverage."
                    )
                    context.discoveries.append(Discovery(
                        id=f"validation-gap://integration/{symbol_id}",
                        kind=DiscoveryKind.VALIDATION_GAP,
                        statement=statement,
                        importance=min(0.5 + 0.05 * count, 0.9),
                        support=DiscoverySupport(
                            fan_out=count,
                            validation_gaps=1,
                        ),
                        evidence=(
                            DiscoveryEvidence(
                                source="operational",
                                source_id=symbol_id,
                                description=f"Symbol '{name}' has fan-out of {count}",
                                evidence_ref=f"operational://dependency/fan-out/{symbol_id}",
                            ),
                            DiscoveryEvidence(
                                source="operational",
                                source_id="validation",
                                description="No integration tests found",
                                evidence_ref="operational://validation/integration",
                            ),
                        ),
                        metadata={
                            "symbol_id": symbol_id,
                            "name": name,
                            "fan_out": count,
                            "has_integration": False,
                        },
                    ))

        # --- Discovery 3: Overall validation gap summary ---
        if total_tests == 0 and len(execution_chains) > 0:
            total_paths = len(execution_chains)
            statement = (
                f"None of the {total_paths} affected execution "
                f"path{'s' if total_paths != 1 else ''} have test coverage."
            )
            context.discoveries.append(Discovery(
                id="validation-gap://none",
                kind=DiscoveryKind.VALIDATION_GAP,
                statement=statement,
                importance=0.9,
                support=DiscoverySupport(
                    execution_reach=total_paths,
                    validation_gaps=total_paths,
                ),
                evidence=(
                    DiscoveryEvidence(
                        source="operational",
                        source_id="validation",
                        description="No tests found for any affected behavior",
                        evidence_ref="operational://validation",
                    ),
                ),
                metadata={
                    "total_paths": total_paths,
                    "unit_count": unit_count,
                    "integration_count": integration_count,
                    "e2e_count": e2e_count,
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
    def _derive_unit_name(symbol_id: str) -> str:
        """Derive a human-readable name from a symbol id."""
        if "://" in symbol_id:
            rest = symbol_id.split("://", 1)[1]
        else:
            rest = symbol_id
        name = rest.split("#")[-1].split("::")[-1]
        return name.replace("_", " ").title()
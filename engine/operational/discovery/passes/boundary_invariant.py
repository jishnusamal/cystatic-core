"""BoundaryInvariantPass — highlights important boundaries that remain unchanged.

Reuses existing compiler outputs:
- APIModel: externally visible interfaces (rest, graphql, rpc, cli, cron, workers)
- ChangeModel: what changed (added, removed, modified symbols)
- EntryPoint: where execution begins
- BehaviorModel: affected behaviors
- DependencyModel.cross_service_references: service boundary crossings

No duplicate graph traversal — all data is read from pre-computed models.
"""

from __future__ import annotations

from engine.operational.discovery.model import (
    Discovery,
    DiscoveryEvidence,
    DiscoveryKind,
    DiscoverySupport,
)
from engine.operational.discovery.passes.base import (
    DiscoveryCompilerPass,
    DiscoveryPassContext,
)


class BoundaryInvariantPass(DiscoveryCompilerPass):
    """Highlights important boundaries that remain unchanged.

    Emits discoveries like:
    - "505 internal symbols changed without modifying the REST API."
    - "No service boundaries were crossed."
    - "No new events were introduced."
    """

    @property
    def name(self) -> str:
        return "boundary_invariant"

    def run(self, context: DiscoveryPassContext) -> DiscoveryPassContext:
        """Emit boundary invariant discoveries from existing compiler outputs."""
        model = context.discovery_model
        if model is None:
            return context

        behavior = model.behavior
        change = model.change
        api = getattr(model, "api", None)
        dependency = getattr(model, "dependency", None)

        if behavior is None or change is None:
            return context

        # --- Discovery 1: Internal changes without API modification ---
        # Count total changed symbols
        added = getattr(change, "added_symbols", ())
        removed = getattr(change, "removed_symbols", ())
        modified = getattr(change, "modified_symbols", ())
        total_changed = len(added) + len(removed) + len(modified)

        # Check if API surface is empty (unchanged)
        api_unchanged = True
        api_endpoint_count = 0
        if api is not None:
            rest = getattr(api, "rest", ())
            graphql = getattr(api, "graphql", ())
            rpc = getattr(api, "rpc", ())
            cli = getattr(api, "cli", ())
            cron = getattr(api, "cron", ())
            workers = getattr(api, "workers", ())
            api_endpoint_count = len(rest) + len(graphql) + len(rpc)
            api_unchanged = api_endpoint_count == 0

        if total_changed > 0 and api_unchanged:
            file_count_hint = ""
            changed_imports = getattr(change, "changed_imports", ())
            if changed_imports:
                files_set = set()
                for imp in changed_imports:
                    f = getattr(imp, "file", None)
                    if f:
                        files_set.add(f)
                if files_set:
                    file_count_hint = f" across {len(files_set)} file{'s' if len(files_set) != 1 else ''}"

            statement = (
                f"{total_changed} internal symbol{'s' if total_changed != 1 else ''} "
                f"changed{file_count_hint} without modifying the public REST API."
            )
            context.discoveries.append(
                Discovery(
                    id="boundary-invariant://api-unchanged",
                    kind=DiscoveryKind.BOUNDARY_INVARIANT,
                    statement=statement,
                    importance=0.85,
                    support=DiscoverySupport(
                        changed_symbol_count=total_changed,
                        external_surface=0,
                    ),
                    evidence=(
                        DiscoveryEvidence(
                            source="change",
                            source_id="change:added",
                            description=f"{len(added)} added symbol(s)",
                            evidence_ref="change://added",
                        ),
                        DiscoveryEvidence(
                            source="change",
                            source_id="change:removed",
                            description=f"{len(removed)} removed symbol(s)",
                            evidence_ref="change://removed",
                        ),
                        DiscoveryEvidence(
                            source="change",
                            source_id="change:modified",
                            description=f"{len(modified)} modified symbol(s)",
                            evidence_ref="change://modified",
                        ),
                        DiscoveryEvidence(
                            source="operational",
                            source_id="api",
                            description="No API endpoints were affected",
                            evidence_ref="operational://api",
                        ),
                    ),
                    metadata={
                        "total_changed": total_changed,
                        "added_count": len(added),
                        "removed_count": len(removed),
                        "modified_count": len(modified),
                        "api_unchanged": True,
                    },
                )
            )

        # --- Discovery 2: No service boundaries crossed ---
        cross_service_count = 0
        if dependency is not None:
            cross_service = getattr(dependency, "cross_service_references", ())
            cross_service_count = len(cross_service)

        if cross_service_count == 0 and total_changed > 0:
            statement = "No service boundaries were crossed."
            context.discoveries.append(
                Discovery(
                    id="boundary-invariant://no-cross-service",
                    kind=DiscoveryKind.BOUNDARY_INVARIANT,
                    statement=statement,
                    importance=0.7,
                    support=DiscoverySupport(
                        changed_symbol_count=total_changed,
                        cross_service_count=0,
                    ),
                    evidence=(
                        DiscoveryEvidence(
                            source="operational",
                            source_id="dependency",
                            description="No cross-service references detected",
                            evidence_ref="operational://dependency/cross-service",
                        ),
                    ),
                    metadata={
                        "cross_service_count": 0,
                        "total_changed": total_changed,
                    },
                )
            )

        # --- Discovery 3: No boundary crossings despite growing execution reach ---
        # Check if there's a non-zero execution depth but zero cross-service
        execution_depth = getattr(behavior, "execution_depth", 0)
        if execution_depth > 0 and cross_service_count == 0:
            statement = (
                f"Execution reaches depth {execution_depth} without crossing "
                f"any service boundary."
            )
            context.discoveries.append(
                Discovery(
                    id="boundary-invariant://contained-depth",
                    kind=DiscoveryKind.BOUNDARY_INVARIANT,
                    statement=statement,
                    importance=0.6,
                    support=DiscoverySupport(
                        propagation_depth=execution_depth,
                        cross_service_count=0,
                    ),
                    evidence=(
                        DiscoveryEvidence(
                            source="behavior",
                            source_id="behavior:depth",
                            description=f"Execution depth of {execution_depth}",
                            evidence_ref="behavior://execution_depth",
                        ),
                    ),
                    metadata={
                        "execution_depth": execution_depth,
                        "cross_service_count": 0,
                    },
                )
            )

        return context

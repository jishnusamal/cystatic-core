"""ReviewContext Compiler — transforms compiler outputs into ReviewContext.

Performs four deterministic stages:
    Pass 1 — Selection: Select only review-relevant information.
    Pass 2 — Normalization: Normalize into ReviewContext schema.
    Pass 3 — Discovery Assembly: Populate discoveries from DiscoveryIR.
    Pass 4 — Reference Assembly: Collect unique references.

The compiler MUST NOT:
    - traverse graphs
    - perform DFS/BFS
    - calculate reachability, fan-in, fan-out, propagation, execution depth
    - calculate validation gaps
    - score or rank discoveries
    - compress discoveries
    - generate summaries, English explanations, markdown, comments, or UI objects
"""
from __future__ import annotations

from typing import Any

from change.model import ChangeModel
from behavior.model import BehaviorModel
from operational.model import OperationalChangeModel
from operational.discovery.model import DiscoveryIR, Discovery as DiscoveryIRDiscovery
from operational.model import EngineeringDiscoveryModel

from .model import (
    ReviewContext,
    ChangeContext,
    ChangeSummary,
    FileChange,
    Change,
    SymbolRef,
    Relationships,
    ChangeImpact,
    ChangeValidation,
    ChangeReferences,
    ExecutionContext,
    ImpactContext,
    StateContext,
    IntegrationContext,
    ValidationContext,
    Discovery,
    Reference,
)


class ReviewContextCompiler:
    """Compiles existing compiler outputs into a ReviewContext.

    The ReviewContext is the public ABI of Factor.
    Everything after ReviewContext is replaceable.

    Inputs: ChangeModel, BehaviorModel, OperationalChangeModel, DiscoveryIR
    Output: ReviewContext
    """

    def compile(
        self,
        change_model: ChangeModel | None = None,
        behavior_model: BehaviorModel | None = None,
        operational_model: OperationalChangeModel | None = None,
        discovery_model: EngineeringDiscoveryModel | None = None,
        discovery_ir: DiscoveryIR | None = None,
    ) -> ReviewContext:
        """Compile compiler outputs into a ReviewContext.

        Args:
            change_model: The ChangeModel from change compilation.
            behavior_model: The BehaviorModel from behavior compilation.
            operational_model: The OperationalChangeModel from operational compilation.
            discovery_model: The EngineeringDiscoveryModel from discovery compilation.
            discovery_ir: The DiscoveryIR from discovery compilation.

        Returns:
            A ReviewContext containing only engineering context.
        """
        # Pass 1: Selection — select review-relevant information
        change_ctx = self._select_change_context(change_model)
        execution_ctx = self._select_execution_context(behavior_model, discovery_model)
        impact_ctx = self._select_impact_context(behavior_model, discovery_model)
        state_ctx = self._select_state_context(operational_model, discovery_model)
        integration_ctx = self._select_integration_context(operational_model, discovery_model)
        validation_ctx = self._select_validation_context(operational_model, discovery_model)

        # Pass 2: Normalization — already done via schema construction above

        # Pass 3: Discovery Assembly — populate from DiscoveryIR directly
        discoveries = self._assemble_discoveries(discovery_ir)

        # Pass 4: Reference Assembly — collect unique references
        references = self._assemble_references(discoveries)

        return ReviewContext(
            change=change_ctx,
            execution=execution_ctx,
            impact=impact_ctx,
            state=state_ctx,
            integration=integration_ctx,
            validation=validation_ctx,
            discoveries=discoveries,
            references=references,
        )

    # -----------------------------------------------------------------------
    # Pass 1 — Selection: ChangeContext
    # -----------------------------------------------------------------------

    def _select_change_context(
        self,
        change_model: ChangeModel | None,
    ) -> ChangeContext:
        """Select change-relevant information from ChangeModel.

        Builds a hierarchical, file-centered structure.
        No compiler-oriented flat lists.
        """
        if change_model is None:
            return ChangeContext()

        # --- Summary ---
        classification = self._determine_classification(change_model)
        scope = self._determine_scope(change_model)
        file_count = change_model.files_changed
        symbol_count = (
            len(change_model.added_symbols)
            + len(change_model.removed_symbols)
            + len(change_model.modified_symbols)
        )
        behavior_count = sum(
            len(ms.changes) for ms in change_model.modified_symbols
        )

        summary = ChangeSummary(
            classification=classification,
            scope=scope,
            file_count=file_count,
            symbol_count=symbol_count,
            behavior_count=behavior_count,
        )

        # --- Files: group changed symbols by file ---
        files: dict[str, list[Change]] = {}

        # Added symbols
        for sym in change_model.added_symbols:
            file_path = sym.file
            if file_path not in files:
                files[file_path] = []
            files[file_path].append(self._build_change(sym, "added"))

        # Removed symbols
        for sym in change_model.removed_symbols:
            file_path = sym.file
            if file_path not in files:
                files[file_path] = []
            files[file_path].append(self._build_change(sym, "removed"))

        # Modified symbols
        for ms in change_model.modified_symbols:
            sym = ms.symbol
            file_path = sym.file
            if file_path not in files:
                files[file_path] = []
            # Extract behavior change type names
            behavior_changes = tuple(type(c).__name__ for c in ms.changes)
            files[file_path].append(self._build_change(sym, "modified", behavior_changes))

        # Build FileChange objects
        file_changes: list[FileChange] = []
        for file_path, changes in files.items():
            # Determine file-level change type
            change_types = {c.change_type for c in changes}
            if len(change_types) > 1:
                file_change_type = "mixed"
            elif "added" in change_types:
                file_change_type = "added"
            elif "removed" in change_types:
                file_change_type = "removed"
            else:
                file_change_type = "modified"

            # Determine language from first symbol
            language = ""
            for c in changes:
                if c.symbol.language:
                    language = c.symbol.language
                    break

            file_changes.append(FileChange(
                path=file_path,
                language=language,
                change_type=file_change_type,
                changes=tuple(changes),
            ))

        return ChangeContext(
            summary=summary,
            files=tuple(file_changes),
        )

    def _build_change(
        self,
        sym: Any,
        change_type: str,
        behavior_changes: tuple[str, ...] = (),
    ) -> Change:
        """Build a Change from a symbol and its change type.

        Only selects existing metadata. No new discovery.
        """
        symbol_ref = SymbolRef(
            id=sym.id,
            name=sym.name,
            kind=sym.kind.value if hasattr(sym.kind, 'value') else str(sym.kind),
            visibility=sym.visibility.value if hasattr(sym.visibility, 'value') else str(sym.visibility),
            language=sym.language if hasattr(sym, 'language') else "",
            location=f"{sym.file}:{sym.range[0]}-{sym.range[1]}" if hasattr(sym, 'range') else sym.file,
        )

        return Change(
            symbol=symbol_ref,
            change_type=change_type,
            behavior_changes=behavior_changes,
        )

    def _determine_classification(self, change_model: ChangeModel) -> str:
        """Determine change classification from existing model data."""
        has_added = bool(change_model.added_symbols)
        has_removed = bool(change_model.removed_symbols)
        has_modified = bool(change_model.modified_symbols)

        if has_added and has_removed:
            return "mixed"
        if has_added and not has_modified:
            return "addition"
        if has_removed and not has_added:
            return "removal"
        return "modification"

    def _determine_scope(self, change_model: ChangeModel) -> str:
        """Determine change scope from existing model data."""
        if change_model.files_changed > 5:
            return "wide"
        if change_model.files_changed > 1:
            return "multi_file"
        return "local"

    # -----------------------------------------------------------------------
    # Pass 1 — Selection: ExecutionContext
    # -----------------------------------------------------------------------

    def _select_execution_context(
        self,
        behavior_model: BehaviorModel | None,
        discovery_model: EngineeringDiscoveryModel | None,
    ) -> ExecutionContext:
        """Select execution-relevant information from BehaviorModel and EngineeringDiscoveryModel.

        Reuses existing values — never recomputes.
        """
        if behavior_model is None and discovery_model is None:
            return ExecutionContext()

        entry_points: list[str] = []
        execution_chains: list[str] = []
        terminal_points: list[str] = []
        reachable_units: list[str] = []
        shared_execution: list[str] = []
        max_execution_depth: int = 0

        # From BehaviorModel
        if behavior_model is not None:
            for ep in behavior_model.entry_points:
                label = ep.route if hasattr(ep, 'route') and ep.route else ep.kind if hasattr(ep, 'kind') else str(ep.id)
                entry_points.append(label)

            for chain in behavior_model.execution_chains:
                label = chain.behavior_id if hasattr(chain, 'behavior_id') else str(chain.id)
                execution_chains.append(label)

            for tp in behavior_model.terminal_points:
                label = tp.kind if hasattr(tp, 'kind') else str(tp.id)
                terminal_points.append(label)

            for ru in behavior_model.reachable_units:
                label = ru.name if hasattr(ru, 'name') else str(ru.id)
                reachable_units.append(label)

            for se in behavior_model.shared_executions:
                label = se.symbol_id if hasattr(se, 'symbol_id') else str(se.id)
                shared_execution.append(label)

            max_execution_depth = behavior_model.execution_depth

        # From EngineeringDiscoveryModel (if available, use as supplement)
        if discovery_model is not None:
            for ep in discovery_model.entry_points:
                label = ep.route if hasattr(ep, 'route') and ep.route else ep.kind if hasattr(ep, 'kind') else str(ep.id)
                if label not in entry_points:
                    entry_points.append(label)

            for chain in discovery_model.execution_chains:
                label = chain.behavior_id if hasattr(chain, 'behavior_id') else str(chain.id)
                if label not in execution_chains:
                    execution_chains.append(label)

            for tp in discovery_model.terminal_points:
                label = tp.kind if hasattr(tp, 'kind') else str(tp.id)
                if label not in terminal_points:
                    terminal_points.append(label)

            for ru in discovery_model.reachable_units:
                label = ru.name if hasattr(ru, 'name') else str(ru.id)
                if label not in reachable_units:
                    reachable_units.append(label)

            for se in discovery_model.shared_executions:
                label = se.symbol_id if hasattr(se, 'symbol_id') else str(se.id)
                if label not in shared_execution:
                    shared_execution.append(label)

            if discovery_model.execution_depth > max_execution_depth:
                max_execution_depth = discovery_model.execution_depth

        return ExecutionContext(
            entry_points=tuple(entry_points),
            execution_chains=tuple(execution_chains),
            terminal_points=tuple(terminal_points),
            reachable_units=tuple(reachable_units),
            shared_execution=tuple(shared_execution),
            max_execution_depth=max_execution_depth,
        )

    # -----------------------------------------------------------------------
    # Pass 1 — Selection: ImpactContext
    # -----------------------------------------------------------------------

    def _select_impact_context(
        self,
        behavior_model: BehaviorModel | None,
        discovery_model: EngineeringDiscoveryModel | None,
    ) -> ImpactContext:
        """Select impact-relevant information.

        Only deterministic relationships. No scoring.
        """
        if behavior_model is None and discovery_model is None:
            return ImpactContext()

        services: list[str] = []
        modules: list[str] = []
        callers: list[str] = []
        dependents: list[str] = []
        cross_service_references: list[str] = []
        propagation: list[str] = []

        fan_in: int = 0
        fan_out: int = 0
        boundary_crossings: int = 0

        # From BehaviorModel — extract module/service names from behaviors
        if behavior_model is not None:
            for behavior in behavior_model.behaviors:
                name = behavior.name if hasattr(behavior, 'name') else str(behavior.id)
                modules.append(name)
                kind = behavior.kind.value if hasattr(behavior.kind, 'value') else str(behavior.kind)
                services.append(kind)

            # Count reachable units as fan-out
            fan_out = len(behavior_model.reachable_units)
            fan_in = len(behavior_model.entry_points)

            # Count boundary crossings from execution chains
            for chain in behavior_model.execution_chains:
                if hasattr(chain, 'boundary_crossings'):
                    boundary_crossings += len(chain.boundary_crossings)

        # From EngineeringDiscoveryModel
        if discovery_model is not None:
            for behavior in discovery_model.get_behaviors():
                name = behavior.name if hasattr(behavior, 'name') else str(behavior.id)
                if name not in modules:
                    modules.append(name)
                kind = behavior.kind.value if hasattr(behavior.kind, 'value') else str(behavior.kind)
                if kind not in services:
                    services.append(kind)

            if discovery_model.execution_chains:
                fan_out = max(fan_out, len(discovery_model.reachable_units))
                fan_in = max(fan_in, len(discovery_model.entry_points))

        return ImpactContext(
            services=tuple(services),
            modules=tuple(modules),
            callers=tuple(callers),
            dependents=tuple(dependents),
            fan_in=fan_in,
            fan_out=fan_out,
            cross_service_references=tuple(cross_service_references),
            boundary_crossings=boundary_crossings,
            propagation=tuple(propagation),
        )

    # -----------------------------------------------------------------------
    # Pass 1 — Selection: StateContext
    # -----------------------------------------------------------------------

    def _select_state_context(
        self,
        operational_model: OperationalChangeModel | None,
        discovery_model: EngineeringDiscoveryModel | None,
    ) -> StateContext:
        """Select state/data-relevant information.

        Reuses Operational Compiler outputs.
        """
        if operational_model is None and discovery_model is None:
            return StateContext()

        models: list[str] = []
        tables: list[str] = []
        reads: list[str] = []
        writes: list[str] = []
        transactions: list[str] = []
        caches: list[str] = []
        external_storage: list[str] = []

        # From OperationalChangeModel data model
        if operational_model is not None and operational_model.data is not None:
            data = operational_model.data
            if hasattr(data, 'models'):
                for m in data.models:
                    name = m.name if hasattr(m, 'name') else str(m)
                    models.append(name)
            if hasattr(data, 'tables'):
                for t in data.tables:
                    name = t.name if hasattr(t, 'name') else str(t)
                    tables.append(name)

        # From EngineeringDiscoveryModel data model
        if discovery_model is not None and discovery_model.data is not None:
            data = discovery_model.data
            if hasattr(data, 'models'):
                for m in data.models:
                    name = m.name if hasattr(m, 'name') else str(m)
                    if name not in models:
                        models.append(name)
            if hasattr(data, 'tables'):
                for t in data.tables:
                    name = t.name if hasattr(t, 'name') else str(t)
                    if name not in tables:
                        tables.append(name)

        return StateContext(
            models=tuple(models),
            tables=tuple(tables),
            reads=tuple(reads),
            writes=tuple(writes),
            transactions=tuple(transactions),
            caches=tuple(caches),
            external_storage=tuple(external_storage),
        )

    # -----------------------------------------------------------------------
    # Pass 1 — Selection: IntegrationContext
    # -----------------------------------------------------------------------

    def _select_integration_context(
        self,
        operational_model: OperationalChangeModel | None,
        discovery_model: EngineeringDiscoveryModel | None,
    ) -> IntegrationContext:
        """Select integration-relevant information.

        Only expose facts. No summaries.
        """
        if operational_model is None and discovery_model is None:
            return IntegrationContext()

        rest: list[str] = []
        events: list[str] = []

        # From OperationalChangeModel API model
        if operational_model is not None and operational_model.api is not None:
            api = operational_model.api
            if hasattr(api, 'endpoints'):
                for ep in api.endpoints:
                    route = ep.route if hasattr(ep, 'route') else str(ep)
                    rest.append(route)

        # From EngineeringDiscoveryModel API model
        if discovery_model is not None and discovery_model.api is not None:
            api = discovery_model.api
            if hasattr(api, 'endpoints'):
                for ep in api.endpoints:
                    route = ep.route if hasattr(ep, 'route') else str(ep)
                    if route not in rest:
                        rest.append(route)

        # From OperationalChangeModel event model
        if operational_model is not None and operational_model.event is not None:
            event = operational_model.event
            if hasattr(event, 'events'):
                for e in event.events:
                    name = e.name if hasattr(e, 'name') else str(e)
                    events.append(name)

        # From EngineeringDiscoveryModel event model
        if discovery_model is not None and discovery_model.event is not None:
            event = discovery_model.event
            if hasattr(event, 'events'):
                for e in event.events:
                    name = e.name if hasattr(e, 'name') else str(e)
                    if name not in events:
                        events.append(name)

        return IntegrationContext(
            rest=tuple(rest),
            events=tuple(events),
        )

    # -----------------------------------------------------------------------
    # Pass 1 — Selection: ValidationContext
    # -----------------------------------------------------------------------

    def _select_validation_context(
        self,
        operational_model: OperationalChangeModel | None,
        discovery_model: EngineeringDiscoveryModel | None,
    ) -> ValidationContext:
        """Select validation-relevant information.

        No recommendations.
        """
        if operational_model is None and discovery_model is None:
            return ValidationContext()

        unit_tests: list[str] = []
        integration_tests: list[str] = []
        validation_gaps: list[str] = []

        # From OperationalChangeModel validation model
        if operational_model is not None and operational_model.validation is not None:
            validation = operational_model.validation
            if hasattr(validation, 'unit_tests'):
                for t in validation.unit_tests:
                    name = t.name if hasattr(t, 'name') else str(t)
                    unit_tests.append(name)
            if hasattr(validation, 'integration_tests'):
                for t in validation.integration_tests:
                    name = t.name if hasattr(t, 'name') else str(t)
                    integration_tests.append(name)

        # From EngineeringDiscoveryModel validation model
        if discovery_model is not None and discovery_model.validation is not None:
            validation = discovery_model.validation
            if hasattr(validation, 'unit_tests'):
                for t in validation.unit_tests:
                    name = t.name if hasattr(t, 'name') else str(t)
                    if name not in unit_tests:
                        unit_tests.append(name)
            if hasattr(validation, 'integration_tests'):
                for t in validation.integration_tests:
                    name = t.name if hasattr(t, 'name') else str(t)
                    if name not in integration_tests:
                        integration_tests.append(name)

        return ValidationContext(
            unit_tests=tuple(unit_tests),
            integration_tests=tuple(integration_tests),
            validation_gaps=tuple(validation_gaps),
        )

    # -----------------------------------------------------------------------
    # Pass 3 — Discovery Assembly
    # -----------------------------------------------------------------------

    def _assemble_discoveries(
        self,
        discovery_ir: DiscoveryIR | None,
    ) -> tuple[Discovery, ...]:
        """Populate ReviewContext.discoveries directly from DiscoveryIR.

        No new discoveries. No filtering beyond deterministic selection.
        Each discovery references supporting compiler artifacts.

        Removes: importance scores, ranking vectors, surprise vectors,
        compression metadata, presentation metadata.
        """
        if discovery_ir is None:
            return ()

        discoveries: list[Discovery] = []

        for d in discovery_ir.discoveries:
            # Build references from evidence
            references: list[Reference] = []
            for evidence in d.evidence:
                ref = Reference(
                    id=evidence.source_id,
                    kind=evidence.source,
                    location=evidence.evidence_ref,
                    compiler_artifact=evidence.source,
                    supporting_nodes=(evidence.description,) if evidence.description else (),
                )
                references.append(ref)

            discovery = Discovery(
                id=d.id,
                kind=d.kind.value if hasattr(d.kind, 'value') else str(d.kind),
                statement=d.statement,
                references=tuple(references),
            )
            discoveries.append(discovery)

        return tuple(discoveries)

    # -----------------------------------------------------------------------
    # Pass 4 — Reference Assembly
    # -----------------------------------------------------------------------

    def _assemble_references(
        self,
        discoveries: tuple[Discovery, ...],
    ) -> tuple[Reference, ...]:
        """Collect unique references required by discoveries.

        Deduplicates by reference id.
        Maintains traceability.
        """
        seen: set[str] = set()
        unique_references: list[Reference] = []

        for discovery in discoveries:
            for ref in discovery.references:
                if ref.id and ref.id not in seen:
                    seen.add(ref.id)
                    unique_references.append(ref)

        return tuple(unique_references)
"""Pass 0 — Normalization.

Responsibility:
    Convert four different compiler summaries (ChangeSummary, BehaviorSummary,
    OperationalSummary, DiscoverySummary) into a single canonical presentation source.

Input Contract:
    EngineeringDiscoveryModel containing:
        - ChangeModel (what changed)
        - BehaviorModel (how execution changes)
        - Operational enrichment models (API, data, event, dependency, validation)
        - Execution abstractions (chains, units, depth)

Output Contract:
    list[NormalizedDiscovery] — every deterministic fact from every compiler
    summary becomes exactly one NormalizedDiscovery.

Transformation:
    Walk each compiler summary. For each deterministic fact:
        1. Assign a stable ID
        2. Determine the semantic kind
        3. Assign a title and description
        4. Attach evidence (source, source_id, description, ref)
        5. Preserve source artifact reference

Algorithm:
    For change_model:
        For each added_symbol -> NormalizedDiscovery(kind="added_symbol", ...)
        For each removed_symbol -> NormalizedDiscovery(kind="removed_symbol", ...)
        For each modified_symbol -> NormalizedDiscovery(kind="modified_symbol", ...)
        For each changed_endpoint -> NormalizedDiscovery(kind="changed_endpoint", ...)
        For each changed_import -> NormalizedDiscovery(kind="changed_import", ...)

    For behavior_model:
        For each behavior -> NormalizedDiscovery(kind="behavior", ...)
        For each entry_point -> NormalizedDiscovery(kind="entry_point", ...)
        For each terminal_point -> NormalizedDiscovery(kind="terminal_point", ...)
        For each shared_execution -> NormalizedDiscovery(kind="shared_execution", ...)

    For execution abstractions:
        If execution_chains exists -> NormalizedDiscovery(kind="execution_chain", ...)
        If reachable_units exists -> NormalizedDiscovery(kind="reachable_units", ...)
        If execution_depth > 0 -> NormalizedDiscovery(kind="execution_depth", ...)

    For enrichment models:
        If api model exists -> NormalizedDiscovery(kind="api_surface", ...)
        If data model exists -> NormalizedDiscovery(kind="data_surface", ...)
        If event model exists -> NormalizedDiscovery(kind="event_surface", ...)
        If dependency model exists -> NormalizedDiscovery(kind="dependency_surface", ...)
        If validation model exists -> NormalizedDiscovery(kind="validation", ...)

Invariants:
    - Every compiler discovery becomes exactly one NormalizedDiscovery.
    - Never lose evidence — evidence is preserved verbatim.
    - Never combine discoveries — no merging at this stage.
    - No ranking, no filtering, no sorting.

Failure Conditions:
    - If discovery_model is None -> return empty list (no error).
    - If change_model is missing sub-fields -> skip gracefully.

Complexity:
    O(N) where N = total deterministic facts across all compiler summaries.

Must Never:
    - Analyze, rank, filter, sort, merge, compress, or summarize.
    - Interpret or infer new facts.
    - Access renderer-specific formats.
"""
from __future__ import annotations

from typing import Any

from operational.model import EngineeringDiscoveryModel
from presentation.model import (
    PresentationEvidence,
    NormalizedDiscovery,
)
from .base import PresentationPassContext, PresentationCompilationPass


class NormalizationPass(PresentationCompilationPass):
    """
    Pass 0: Normalizes four compiler summaries into a single canonical source.

    This pass exists so every pass after it operates over one stable model,
    not four unrelated compiler artifacts.
    """

    @property
    def name(self) -> str:
        return "normalization"

    def run(self, context: PresentationPassContext) -> PresentationPassContext:
        """Normalize all compiler summaries into a single discovery list."""
        discovery_model = context.discovery_model
        if discovery_model is None:
            return context

        normalized: list[NormalizedDiscovery] = []
        id_counter: int = 0

        def _next_id(source: str) -> str:
            nonlocal id_counter
            id_counter += 1
            return f"normalized://{source}/{id_counter}"

        # Normalize: Change Summary
        normalized.extend(self._normalize_change_summary(
            discovery_model, _next_id
        ))

        # Normalize: Behavior Summary
        normalized.extend(self._normalize_behavior_summary(
            discovery_model, _next_id
        ))

        # Normalize: Execution abstractions
        normalized.extend(self._normalize_execution_summary(
            discovery_model, _next_id
        ))

        # Normalize: Operational enrichment models
        normalized.extend(self._normalize_operational_summary(
            discovery_model, _next_id
        ))

        context.normalized_discoveries = normalized
        return context

    def _normalize_change_summary(
        self,
        model: EngineeringDiscoveryModel,
        next_id: Any,
    ) -> list[NormalizedDiscovery]:
        """Normalize change model into normalized discoveries."""
        results: list[NormalizedDiscovery] = []
        change = model.change

        if change is None:
            return results

        # Added symbols
        for s in getattr(change, 'added_symbols', ()):
            results.append(NormalizedDiscovery(
                id=next_id("change"),
                kind="added_symbol",
                title=f"Added: {s.name}",
                description=f"Added symbol '{s.name}' ({s.kind})",
                source="change",
                evidence=(PresentationEvidence(
                    source="change",
                    source_id=s.id,
                    description=f"Added symbol: {s.name} ({s.kind})",
                    evidence_ref=f"change://added/{s.id}",
                ),),
                metadata={"symbol_id": s.id, "name": s.name, "kind": str(s.kind)},
            ))

        # Removed symbols
        for s in getattr(change, 'removed_symbols', ()):
            results.append(NormalizedDiscovery(
                id=next_id("change"),
                kind="removed_symbol",
                title=f"Removed: {s.name}",
                description=f"Removed symbol '{s.name}' ({s.kind})",
                source="change",
                evidence=(PresentationEvidence(
                    source="change",
                    source_id=s.id,
                    description=f"Removed symbol: {s.name} ({s.kind})",
                    evidence_ref=f"change://removed/{s.id}",
                ),),
                metadata={"symbol_id": s.id, "name": s.name, "kind": str(s.kind)},
            ))

        # Modified symbols
        for m in getattr(change, 'modified_symbols', ()):
            symbol = m.symbol
            change_count = len(getattr(m, 'changes', ()))
            results.append(NormalizedDiscovery(
                id=next_id("change"),
                kind="modified_symbol",
                title=f"Modified: {symbol.name}",
                description=f"Modified symbol '{symbol.name}' ({change_count} change(s))",
                source="change",
                evidence=(PresentationEvidence(
                    source="change",
                    source_id=symbol.id,
                    description=f"Modified symbol: {symbol.name} ({change_count} change(s))",
                    evidence_ref=f"change://modified/{symbol.id}",
                ),),
                metadata={"symbol_id": symbol.id, "name": symbol.name, "change_count": change_count},
            ))

        # Changed endpoints
        for ep in getattr(change, 'changed_endpoints', ()):
            old = f"{ep.old_method or ''} {ep.old_endpoint or ''}".strip()
            new = f"{ep.new_method or ''} {ep.new_endpoint or ''}".strip()
            results.append(NormalizedDiscovery(
                id=next_id("change"),
                kind="changed_endpoint",
                title=f"Endpoint: {new or old}",
                description=f"Endpoint changed: {old} -> {new}",
                source="change",
                evidence=(PresentationEvidence(
                    source="change",
                    source_id=ep.symbol_id,
                    description=f"Endpoint {ep.change_type}: {old} -> {new}",
                    evidence_ref=f"change://endpoint/{ep.symbol_id}",
                ),),
                metadata={
                    "symbol_id": ep.symbol_id,
                    "old_endpoint": ep.old_endpoint,
                    "new_endpoint": ep.new_endpoint,
                    "change_type": ep.change_type,
                },
            ))

        # Changed imports
        for imp in getattr(change, 'changed_imports', ()):
            old = imp.old_import or ""
            new = imp.new_import or ""
            results.append(NormalizedDiscovery(
                id=next_id("change"),
                kind="changed_import",
                title=f"Import: {new or old}",
                description=f"Import {imp.change_type}: {old} -> {new}",
                source="change",
                evidence=(PresentationEvidence(
                    source="change",
                    source_id=imp.file,
                    description=f"Import {imp.change_type}: {old} -> {new}",
                    evidence_ref=f"change://import/{imp.file}",
                ),),
                metadata={"file": imp.file, "old_import": old, "new_import": new, "change_type": imp.change_type},
            ))

        return results

    def _normalize_behavior_summary(
        self,
        model: EngineeringDiscoveryModel,
        next_id: Any,
    ) -> list[NormalizedDiscovery]:
        """Normalize behavior model into normalized discoveries."""
        results: list[NormalizedDiscovery] = []
        behavior = model.behavior

        if behavior is None:
            return results

        # Individual behaviors
        for b in getattr(behavior, 'behaviors', ()):
            evidence = [
                PresentationEvidence(
                    source="behavior",
                    source_id=b.id,
                    description=f"Behavior: {b.name} ({b.kind.value})",
                    evidence_ref=f"behavior://{b.id}",
                ),
            ]
            if hasattr(b, 'evidence') and b.evidence is not None:
                ev = b.evidence
                if hasattr(ev, 'file_location') and ev.file_location:
                    evidence.append(PresentationEvidence(
                        source="behavior",
                        source_id=b.id,
                        description=f"Evidence: {ev.file_location.file}:{ev.file_location.start_line}",
                        evidence_ref=f"behavior://evidence/{b.id}",
                    ))
            results.append(NormalizedDiscovery(
                id=next_id("behavior"),
                kind="behavior",
                title=f"Behavior: {b.name}",
                description=f"Affected behavior '{b.name}' (kind={b.kind.value})",
                source="behavior",
                evidence=tuple(evidence),
                metadata={
                    "behavior_id": b.id,
                    "name": b.name,
                    "kind": b.kind.value,
                    "entry_point": b.entry_point,
                    "changed_symbols": list(getattr(b, 'changed_symbol_ids', ())),
                },
            ))

        # Entry points
        for ep in getattr(behavior, 'entry_points', ()):
            results.append(NormalizedDiscovery(
                id=next_id("behavior"),
                kind="entry_point",
                title=f"Entry Point: {ep.route}",
                description=f"Entry point '{ep.route}' ({ep.kind})",
                source="behavior",
                evidence=(PresentationEvidence(
                    source="behavior",
                    source_id=ep.id,
                    description=f"Entry point: {ep.route} ({ep.kind})",
                    evidence_ref=f"behavior://entry_point/{ep.id}",
                ),),
                metadata={"entry_point_id": ep.id, "route": ep.route, "kind": ep.kind},
            ))

        # Terminal points
        for tp in getattr(behavior, 'terminal_points', ()):
            results.append(NormalizedDiscovery(
                id=next_id("behavior"),
                kind="terminal_point",
                title=f"Terminal Point: {tp.symbol_id}",
                description=f"Terminal point at '{tp.symbol_id}' ({tp.kind})",
                source="behavior",
                evidence=(PresentationEvidence(
                    source="behavior",
                    source_id=tp.id,
                    description=f"Terminal point: {tp.symbol_id} ({tp.kind})",
                    evidence_ref=f"behavior://terminal_point/{tp.id}",
                ),),
                metadata={"terminal_point_id": tp.id, "symbol_id": tp.symbol_id, "kind": tp.kind},
            ))

        # Shared executions
        for se in getattr(behavior, 'shared_executions', ()):
            used_by_count = len(getattr(se, 'used_by', ()))
            results.append(NormalizedDiscovery(
                id=next_id("behavior"),
                kind="shared_execution",
                title=f"Shared: {se.symbol_id}",
                description=f"Shared execution '{se.symbol_id}' (used by {used_by_count} behavior(s))",
                source="behavior",
                evidence=(PresentationEvidence(
                    source="behavior",
                    source_id=se.id,
                    description=f"Shared execution: {se.symbol_id} (used by {used_by_count})",
                    evidence_ref=f"behavior://shared/{se.id}",
                ),),
                metadata={"shared_id": se.id, "symbol_id": se.symbol_id, "used_by_count": used_by_count},
            ))

        return results

    def _normalize_execution_summary(
        self,
        model: EngineeringDiscoveryModel,
        next_id: Any,
    ) -> list[NormalizedDiscovery]:
        """Normalize execution abstractions into normalized discoveries."""
        results: list[NormalizedDiscovery] = []

        # Execution chains
        chains = getattr(model, 'execution_chains', ())
        if chains:
            total_units = 0
            for chain in chains:
                total_units += len(getattr(chain, 'units', ()))
            results.append(NormalizedDiscovery(
                id=next_id("execution"),
                kind="execution_chain",
                title="Execution Chains",
                description=f"{len(chains)} execution chain(s) with {total_units} unit(s)",
                source="behavior",
                evidence=tuple(
                    PresentationEvidence(
                        source="behavior",
                        source_id=chain.id,
                        description=f"Execution chain: {chain.behavior_id} ({len(getattr(chain, 'units', ()))} unit(s))",
                        evidence_ref=f"behavior://chain/{chain.id}",
                    )
                    for chain in chains
                ),
                metadata={"chain_count": len(chains), "unit_count": total_units},
            ))

        # Reachable units
        units = getattr(model, 'reachable_units', ())
        if units:
            results.append(NormalizedDiscovery(
                id=next_id("execution"),
                kind="reachable_units",
                title="Reachable Units",
                description=f"{len(units)} execution unit(s) reachable from changed symbols",
                source="behavior",
                evidence=tuple(
                    PresentationEvidence(
                        source="behavior",
                        source_id=u.id,
                        description=f"Reachable unit: {u.name} (order {u.order})",
                        evidence_ref=f"behavior://reachable/{u.id}",
                    )
                    for u in units
                ),
                metadata={"unit_count": len(units)},
            ))

        # Execution depth
        depth = getattr(model, 'execution_depth', 0)
        if depth > 0:
            results.append(NormalizedDiscovery(
                id=next_id("execution"),
                kind="execution_depth",
                title="Execution Depth",
                description=f"Maximum execution depth of {depth} across all behaviors",
                source="behavior",
                evidence=(PresentationEvidence(
                    source="behavior",
                    source_id="execution_depth",
                    description=f"Max depth: {depth}",
                    evidence_ref="behavior://execution_depth",
                ),),
                metadata={"depth": depth},
            ))

        return results

    def _normalize_operational_summary(
        self,
        model: EngineeringDiscoveryModel,
        next_id: Any,
    ) -> list[NormalizedDiscovery]:
        """Normalize operational enrichment models into normalized discoveries."""
        results: list[NormalizedDiscovery] = []

        # API surface
        api = getattr(model, 'api', None)
        if api is not None:
            api_count = self._count_attribute(api, ('endpoints', 'routes'))
            results.append(NormalizedDiscovery(
                id=next_id("operational"),
                kind="api_surface",
                title="API Surface",
                description=f"{api_count} API endpoint(s) affected",
                source="operational",
                evidence=(PresentationEvidence(
                    source="operational",
                    source_id="api",
                    description=f"API model present with {api_count} endpoint(s)",
                    evidence_ref="operational://api",
                ),),
                metadata={"endpoint_count": api_count},
            ))

        # Data surface
        data = getattr(model, 'data', None)
        if data is not None:
            data_count = self._count_attribute(data, ('entities', 'tables', 'collections'))
            results.append(NormalizedDiscovery(
                id=next_id("operational"),
                kind="data_surface",
                title="Data Surface",
                description=f"{data_count} data entity/table(s) affected",
                source="operational",
                evidence=(PresentationEvidence(
                    source="operational",
                    source_id="data",
                    description=f"Data model present with {data_count} entity/table(s)",
                    evidence_ref="operational://data",
                ),),
                metadata={"entity_count": data_count},
            ))

        # Event surface
        event = getattr(model, 'event', None)
        if event is not None:
            event_count = self._count_attribute(event, ('events', 'channels'))
            results.append(NormalizedDiscovery(
                id=next_id("operational"),
                kind="event_surface",
                title="Event Surface",
                description=f"{event_count} event(s) affected",
                source="operational",
                evidence=(PresentationEvidence(
                    source="operational",
                    source_id="event",
                    description=f"Event model present with {event_count} event(s)",
                    evidence_ref="operational://event",
                ),),
                metadata={"event_count": event_count},
            ))

        # Dependency surface
        dep = getattr(model, 'dependency', None)
        if dep is not None:
            dep_count = self._count_attribute(dep, ('dependencies', 'changes'))
            results.append(NormalizedDiscovery(
                id=next_id("operational"),
                kind="dependency_surface",
                title="Dependency Surface",
                description=f"{dep_count} dependency/dependency change(s) detected",
                source="operational",
                evidence=(PresentationEvidence(
                    source="operational",
                    source_id="dependency",
                    description=f"Dependency model present with {dep_count} change(s)",
                    evidence_ref="operational://dependency",
                ),),
                metadata={"dependency_count": dep_count},
            ))

        # Validation
        validation = getattr(model, 'validation', None)
        if validation is not None:
            covered = self._count_attribute(validation, ('covered_paths', 'covered'))
            missing = self._count_attribute(
                validation, ('missing_coverage', 'uncovered', 'gaps')
            )
            if covered > 0:
                results.append(NormalizedDiscovery(
                    id=next_id("operational"),
                    kind="validation_coverage",
                    title="Validated Execution Paths",
                    description=f"{covered} execution path(s) have test coverage",
                    source="operational",
                    evidence=(PresentationEvidence(
                        source="operational",
                        source_id="validation",
                        description=f"{covered} covered path(s)",
                        evidence_ref="operational://validation/covered",
                    ),),
                    metadata={"covered_count": covered},
                ))
            if missing > 0:
                results.append(NormalizedDiscovery(
                    id=next_id("operational"),
                    kind="validation_gap",
                    title="Missing Coverage",
                    description=f"{missing} execution path(s) lack test coverage",
                    source="operational",
                    evidence=(PresentationEvidence(
                        source="operational",
                        source_id="validation",
                        description=f"{missing} uncovered path(s)",
                        evidence_ref="operational://validation/missing",
                    ),),
                    metadata={"missing_count": missing},
                ))

        return results

    @staticmethod
    def _count_attribute(obj: object, attr_names: tuple[str, ...]) -> int:
        """Count items from the first matching attribute name."""
        for name in attr_names:
            if hasattr(obj, name):
                items = getattr(obj, name)
                if isinstance(items, (list, tuple, set, frozenset)):
                    return len(items)
                if hasattr(items, '__len__'):
                    return len(items)
                return 1
        return 0
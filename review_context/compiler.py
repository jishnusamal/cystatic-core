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
    ExecutionContext,
    EntryPointExecution,
    ExecutionStep,
    SymbolReference,
    ReachedComponents,
    DeepestExecution,
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
        execution_ctx = self._select_execution_context(
            behavior_model, discovery_model, change_model
        )

        # Pass 2: Normalization — already done via schema construction above

        # Pass 3: Discovery Assembly — populate from DiscoveryIR directly
        discoveries = self._assemble_discoveries(discovery_ir)

        # Pass 4: Reference Assembly — collect unique references
        references = self._assemble_references(discoveries)

        return ReviewContext(
            change=change_ctx,
            execution=execution_ctx,
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
    # Pass 1 — Selection: ExecutionContext (hierarchical execution graph)
    # -----------------------------------------------------------------------

    def _select_execution_context(
        self,
        behavior_model: BehaviorModel | None,
        discovery_model: EngineeringDiscoveryModel | None,
        change_model: ChangeModel | None = None,
    ) -> ExecutionContext:
        """Select execution-relevant information and build a hierarchical execution graph.

        Organizes execution information around entry points, each with its own
        execution chain containing per-step metadata (changed, shared, symbol info,
        reached components).

        Reuses existing values — never recomputes.
        No graph traversal inside ReviewContext.
        """
        if behavior_model is None and discovery_model is None:
            return ExecutionContext()

        # Collect changed symbol IDs for the 'changed' flag
        changed_symbol_ids: set[str] = set()
        if change_model is not None:
            for sym in change_model.added_symbols:
                changed_symbol_ids.add(sym.id)
            for sym in change_model.removed_symbols:
                changed_symbol_ids.add(sym.id)
            for ms in change_model.modified_symbols:
                changed_symbol_ids.add(ms.symbol.id)

        # Collect shared symbol IDs for the 'shared' flag
        shared_symbol_ids: set[str] = set()
        if behavior_model is not None:
            for se in behavior_model.shared_executions:
                shared_symbol_ids.add(se.symbol_id)
        if discovery_model is not None:
            for se in discovery_model.shared_executions:
                shared_symbol_ids.add(se.symbol_id)

        # Build a symbol lookup from the repository model (if available)
        symbol_lookup: dict[str, Any] = {}
        repo_model = None
        if discovery_model is not None and discovery_model.repository is not None:
            repo_model = discovery_model.repository
        if repo_model is not None and hasattr(repo_model, 'symbols'):
            for sym in repo_model.symbols:
                symbol_lookup[sym.id] = sym

        # Build a map of behavior_id -> behavior kind (for reaches.service)
        behavior_kind_map: dict[str, str] = {}
        if behavior_model is not None:
            for b in behavior_model.behaviors:
                behavior_kind_map[b.id] = b.kind.value if hasattr(b.kind, 'value') else str(b.kind)
        if discovery_model is not None:
            for b in discovery_model.get_behaviors():
                if b.id not in behavior_kind_map:
                    behavior_kind_map[b.id] = b.kind.value if hasattr(b.kind, 'value') else str(b.kind)

        # Build a map of behavior_id -> behavior name (for reaches.module)
        behavior_name_map: dict[str, str] = {}
        if behavior_model is not None:
            for b in behavior_model.behaviors:
                behavior_name_map[b.id] = b.name
        if discovery_model is not None:
            for b in discovery_model.get_behaviors():
                if b.id not in behavior_name_map:
                    behavior_name_map[b.id] = b.name

        # Build a map of behavior_id -> terminal point kind
        terminal_by_behavior: dict[str, str] = {}
        if behavior_model is not None:
            for tp in behavior_model.terminal_points:
                terminal_by_behavior[tp.behavior_id] = tp.kind
        if discovery_model is not None:
            for tp in discovery_model.terminal_points:
                terminal_by_behavior[tp.behavior_id] = tp.kind

        # Build a map of behavior_id -> execution chain units
        chain_units_by_behavior: dict[str, list[Any]] = {}
        if behavior_model is not None:
            for chain in behavior_model.execution_chains:
                chain_units_by_behavior[chain.behavior_id] = list(chain.units)
        if discovery_model is not None:
            for chain in discovery_model.execution_chains:
                if chain.behavior_id not in chain_units_by_behavior:
                    chain_units_by_behavior[chain.behavior_id] = list(chain.units)

        # Build entry point executions
        entry_point_executions: list[EntryPointExecution] = []
        deepest_depth = 0
        deepest_ep = ""

        # Collect all entry points (from behavior_model first, then discovery_model)
        all_entry_points: list[Any] = []
        if behavior_model is not None:
            all_entry_points.extend(behavior_model.entry_points)
        if discovery_model is not None:
            for ep in discovery_model.entry_points:
                if ep.id not in {e.id for e in all_entry_points}:
                    all_entry_points.append(ep)

        for ep in all_entry_points:
            behavior_id = ep.behavior_id if hasattr(ep, 'behavior_id') else ""
            endpoint = ep.route if hasattr(ep, 'route') and ep.route else (
                ep.kind if hasattr(ep, 'kind') else str(ep.id)
            )
            method = self._extract_method(ep)
            path = ep.route if hasattr(ep, 'route') else endpoint

            # Build execution chain steps from the behavior's execution units
            units = chain_units_by_behavior.get(behavior_id, [])
            steps: list[ExecutionStep] = []
            max_depth = 0

            for unit in units:
                symbol_id = unit.symbol_id if hasattr(unit, 'symbol_id') else ""
                depth = unit.order if hasattr(unit, 'order') else 0
                if depth > max_depth:
                    max_depth = depth

                # Look up symbol metadata from repository model
                sym_obj = symbol_lookup.get(symbol_id)
                sym_name = unit.name if hasattr(unit, 'name') else (
                    sym_obj.name if sym_obj else symbol_id
                )
                sym_kind = sym_obj.kind.value if sym_obj and hasattr(sym_obj.kind, 'value') else (
                    str(sym_obj.kind) if sym_obj else ""
                )
                sym_location = (
                    f"{sym_obj.file}:{sym_obj.range[0]}-{sym_obj.range[1]}"
                    if sym_obj and hasattr(sym_obj, 'file')
                    else ""
                )

                # Build reached components from behavior metadata
                reaches = ReachedComponents(
                    service=behavior_kind_map.get(behavior_id, ""),
                    module=behavior_name_map.get(behavior_id, ""),
                    package="",
                )

                step = ExecutionStep(
                    behavior=behavior_id,
                    symbol=SymbolReference(
                        id=symbol_id,
                        name=sym_name,
                        kind=sym_kind,
                        location=sym_location,
                    ),
                    kind=sym_kind,
                    depth=depth,
                    changed=symbol_id in changed_symbol_ids,
                    shared=symbol_id in shared_symbol_ids,
                    reaches=reaches,
                    references=(unit.id,) if hasattr(unit, 'id') and unit.id else (),
                )
                steps.append(step)

            # Determine terminal kind for this behavior
            terminal = terminal_by_behavior.get(behavior_id, "")

            # Build references
            ep_refs: list[str] = [ep.id] if hasattr(ep, 'id') and ep.id else []
            if behavior_id:
                ep_refs.append(behavior_id)

            ep_execution = EntryPointExecution(
                endpoint=endpoint,
                method=method,
                path=path,
                execution_chain=tuple(steps),
                terminal=terminal,
                max_depth=max_depth,
                references=tuple(ep_refs),
            )
            entry_point_executions.append(ep_execution)

            # Track deepest execution
            if max_depth > deepest_depth:
                deepest_depth = max_depth
                deepest_ep = endpoint

        # Build deepest execution
        deepest = DeepestExecution(
            entry_point=deepest_ep,
            depth=deepest_depth,
            references=(deepest_ep,) if deepest_ep else (),
        )

        return ExecutionContext(
            entry_points=tuple(entry_point_executions),
            deepest_execution=deepest,
        )

    def _extract_method(self, ep: Any) -> str:
        """Extract HTTP method or trigger type from an entry point."""
        kind = ep.kind if hasattr(ep, 'kind') else ""
        route = ep.route if hasattr(ep, 'route') else ""

        # Try to extract method from route (e.g., "POST /test" -> "POST")
        if " " in route:
            parts = route.split(" ", 1)
            return parts[0]

        # Map from entry point kind
        kind_to_method = {
            "REST_ENDPOINT": "POST",
            "GRAPHQL_RESOLVER": "POST",
            "RPC_HANDLER": "RPC",
            "CLI_COMMAND": "CLI",
            "SCHEDULED_JOB": "SCHEDULE",
            "WORKER_ENTRY": "WORKER",
            "EVENT_CONSUMER": "EVENT",
        }
        return kind_to_method.get(kind, kind)

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
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
from discovery.model import DiscoveryModel, Discovery as DiscoveryModelDiscovery
from operational.discovery.model import DiscoveryIR, Discovery as OldDiscovery

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

# Maximum number of references to expose per discovery in ReviewContext.
# The compiler computes the complete set internally, but only a representative
# subset is exported to keep the payload compact.
MAX_DISCOVERY_REFERENCES = 10


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
        discovery_model: DiscoveryModel | DiscoveryIR | None = None,
    ) -> ReviewContext:
        """Compile compiler outputs into a ReviewContext.

        Args:
            change_model: The ChangeModel from change compilation.
            behavior_model: The BehaviorModel from behavior compilation.
            operational_model: The OperationalChangeModel from operational compilation.
            discovery_model: The DiscoveryModel from discovery compilation.

        Returns:
            A ReviewContext containing only engineering context.
        """
        # Pass 1: Selection — select review-relevant information
        change_ctx = self._select_change_context(change_model)
        execution_ctx = self._select_execution_context(
            behavior_model, operational_model, change_model
        )

        # Pass 2: Normalization — already done via schema construction above

        # Pass 3: Discovery Assembly — populate from DiscoveryModel directly
        discoveries = self._assemble_discoveries(discovery_model)

        return ReviewContext(
            change=change_ctx,
            execution=execution_ctx,
            discoveries=discoveries,
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
        operational_model: OperationalChangeModel | None,
        change_model: ChangeModel | None = None,
    ) -> ExecutionContext:
        """Select execution-relevant information and build a hierarchical execution graph.

        Organizes execution information around entry points, each with its own
        execution chain containing per-step metadata (changed, shared, symbol info,
        reached components).

        Reuses existing values — never recomputes.
        No graph traversal inside ReviewContext.
        """
        if behavior_model is None:
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

        # Build a symbol lookup from the repository model (if available)
        symbol_lookup: dict[str, Any] = {}
        repo_model = None
        if operational_model is not None and operational_model.repository is not None:
            repo_model = operational_model.repository
        if repo_model is not None and hasattr(repo_model, 'symbols'):
            for sym in repo_model.symbols:
                symbol_lookup[sym.id] = sym

        # Build a map of behavior_id -> behavior kind (for reaches.service)
        behavior_kind_map: dict[str, str] = {}
        if behavior_model is not None:
            for b in behavior_model.behaviors:
                behavior_kind_map[b.id] = b.kind.value if hasattr(b.kind, 'value') else str(b.kind)

        # Build a map of behavior_id -> behavior name (for reaches.module)
        behavior_name_map: dict[str, str] = {}
        if behavior_model is not None:
            for b in behavior_model.behaviors:
                behavior_name_map[b.id] = b.name

        # Build a map of behavior_id -> terminal point kind
        terminal_by_behavior: dict[str, str] = {}
        if behavior_model is not None:
            for tp in behavior_model.terminal_points:
                terminal_by_behavior[tp.behavior_id] = tp.kind

        # Build a map of behavior_id -> execution chain units
        chain_units_by_behavior: dict[str, list[Any]] = {}
        if behavior_model is not None:
            for chain in behavior_model.execution_chains:
                chain_units_by_behavior[chain.behavior_id] = list(chain.units)

        # Build entry point executions
        entry_point_executions: list[EntryPointExecution] = []
        deepest_depth = 0
        deepest_ep = ""

        # Collect all entry points from behavior_model
        all_entry_points: list[Any] = []
        if behavior_model is not None:
            all_entry_points.extend(behavior_model.entry_points)

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
        discovery_model: DiscoveryModel | DiscoveryIR | None,
    ) -> tuple[Discovery, ...]:
        """Populate ReviewContext.discoveries from DiscoveryModel or DiscoveryIR.

        Supports both the new DiscoveryModel (discovery.model) and the legacy
        DiscoveryIR (operational.discovery.model) for backward compatibility.

        No new discoveries. No filtering beyond deterministic selection.
        Each discovery references supporting compiler artifacts.

        References are deduplicated, deterministically ranked, and truncated
        to at most MAX_DISCOVERY_REFERENCES per discovery. The total count
        is preserved in reference_count.
        """
        if discovery_model is None:
            return ()

        discoveries: list[Discovery] = []

        # Determine which type of model we have
        if isinstance(discovery_model, DiscoveryIR):
            # Legacy DiscoveryIR from operational.discovery.model
            for d in discovery_model.discoveries:
                # Build references from evidence
                all_references: list[Reference] = []
                for ev in d.evidence:
                    reference = Reference(
                        id=ev.source_id,
                        kind=ev.source,
                        location=ev.evidence_ref,
                        compiler_artifact=ev.source,
                        supporting_nodes=(),
                    )
                    all_references.append(reference)

                # Convert support to facts dict
                facts_dict: dict[str, Any] = {}
                if d.support:
                    facts_dict = {
                        "execution_reach": d.support.execution_reach,
                        "fan_in": d.support.fan_in,
                        "fan_out": d.support.fan_out,
                        "propagation_depth": d.support.propagation_depth,
                        "boundary_crossings": d.support.boundary_crossings,
                        "external_surface": d.support.external_surface,
                        "data_surface": d.support.data_surface,
                        "event_surface": d.support.event_surface,
                        "validation_coverage": d.support.validation_coverage,
                        "validation_gaps": d.support.validation_gaps,
                        "shared_by_count": d.support.shared_by_count,
                        "cross_service_count": d.support.cross_service_count,
                        "changed_symbol_count": d.support.changed_symbol_count,
                        "changed_file_count": d.support.changed_file_count,
                    }

                # Deduplicate, rank, and truncate references
                total_count = len(all_references)
                selected = self._select_representative_references(all_references)

                discovery = Discovery(
                    id=d.id,
                    kind=d.kind.value if hasattr(d.kind, 'value') else str(d.kind),
                    statement=d.statement,
                    facts=facts_dict,
                    reference_count=total_count,
                    references=tuple(selected),
                )
                discoveries.append(discovery)
        else:
            # New DiscoveryModel from discovery.model
            for d_new in discovery_model.discoveries:
                # Build references from discovery references
                refs_new: list[Reference] = []
                for ref in d_new.references:
                    reference = Reference(
                        id=ref.artifact_id,
                        kind=ref.artifact_type,
                        location=ref.location,
                        compiler_artifact=ref.artifact_type,
                        supporting_nodes=(),
                    )
                    refs_new.append(reference)

                # Convert DiscoveryFact to dict for stable ABI
                facts_dict_new: dict[str, Any] = {}
                if d_new.facts:
                    facts_dict_new = {
                        "shared_symbol_ids": d_new.facts.shared_symbol_ids,
                        "behavior_count": d_new.facts.behavior_count,
                        "untested_symbol_ids": d_new.facts.untested_symbol_ids,
                        "validation_coverage_ratio": d_new.facts.validation_coverage_ratio,
                        "crossed_boundaries": d_new.facts.crossed_boundaries,
                        "service_transitions": d_new.facts.service_transitions,
                        "related_symbol_pairs": d_new.facts.related_symbol_pairs,
                        "relationship_type": d_new.facts.relationship_type,
                        "max_depth": d_new.facts.max_depth,
                        "deep_paths": d_new.facts.deep_paths,
                        "shared_dependencies": d_new.facts.shared_dependencies,
                        "dependency_count": d_new.facts.dependency_count,
                        "published_events": d_new.facts.published_events,
                        "event_handlers": d_new.facts.event_handlers,
                        "mutated_state": d_new.facts.mutated_state,
                        "mutation_sources": d_new.facts.mutation_sources,
                        "changed_interfaces": d_new.facts.changed_interfaces,
                        "interface_types": d_new.facts.interface_types,
                    }
                
                # Deduplicate, rank, and truncate references
                total_count = len(refs_new)
                selected = self._select_representative_references(refs_new)

                discovery = Discovery(
                    id=d_new.id,
                    kind=d_new.kind.value if hasattr(d_new.kind, 'value') else str(d_new.kind),
                    statement="",  # No statements in new model
                    facts=facts_dict_new,
                    reference_count=total_count,
                    references=tuple(selected),
                )
                discoveries.append(discovery)

        return tuple(discoveries)

    def _select_representative_references(
        self,
        references: list[Reference],
    ) -> list[Reference]:
        """Deduplicate, rank, and select representative references.

        Selection priority (highest to lowest):
            1. Changed symbols (kind == "change")
            2. Public entrypoints (kind == "behavior" or "entry_point")
            3. Cross-boundary nodes (kind == "boundary" or "operational")
            4. High fan-in / high fan-out nodes (kind == "discovery")
            5. Representative implementation nodes (kind == "symbol" or "execution")
            6. Everything else

        Deterministic: same input always produces same output.
        """
        # Step 1: Deduplicate by id, preserving first occurrence order
        seen: set[str] = set()
        unique: list[Reference] = []
        for ref in references:
            if ref.id and ref.id not in seen:
                seen.add(ref.id)
                unique.append(ref)

        # Step 2: Rank by priority tiers
        def _priority_tier(ref: Reference) -> int:
            kind = ref.kind.lower()
            if kind == "change":
                return 0
            if kind in ("behavior", "entry_point", "endpoint"):
                return 1
            if kind in ("boundary", "operational", "cross_service"):
                return 2
            if kind in ("discovery", "fan_in", "fan_out"):
                return 3
            if kind in ("symbol", "execution", "unit"):
                return 4
            return 5

        # Sort by priority tier, then by id for determinism within tiers
        unique.sort(key=lambda r: (_priority_tier(r), r.id))

        # Step 3: Truncate to MAX_DISCOVERY_REFERENCES
        return unique[:MAX_DISCOVERY_REFERENCES]

    # NOTE: Pass 4 (Reference Assembly) was removed. Top-level references
    # are no longer collected. Each section owns its own supporting evidence.
    # Discoveries contain their own references, execution contains its own
    # evidence, etc.

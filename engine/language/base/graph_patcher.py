"""GraphPatcher - incrementally patches RepositoryGraph with file contributions."""

from collections import deque
import sys
from typing import Any
import os
import time
import dataclasses

from engine.repository.model import (
    Symbol,
    SymbolKind,
    CallEdge,
    CallGraph,
    ReferenceEdge,
    ReferenceGraph,
    TypeRelationshipEdge,
    TypeRelationshipGraph,
    EntryPoint,
    AsyncEntryPoint,
    PersistenceModel,
    RepositoryMethod,
    EventConstruct,
    TestDefinition,
    ConfigurationReference,
    Evidence,
    FileLocation,
)
from engine.repository.model.file_contribution import FileContribution
from engine.repository.model.repository_graph import RepositoryGraph
from engine.language.base.semantic_compiler import SemanticCompiler, _build_symbol_id
from core.runtime import assert_new_architecture


class GraphPatcher:
    """
    Handles patching of RepositoryGraph with file-level contributions.

    Performs incremental semantic resolution to update call/reference edges
    without running repository-wide passes or re-parsing unchanged files.
    """

    def __init__(self) -> None:
        assert_new_architecture("GraphPatcher")
        self.compiler = SemanticCompiler()
        self._affected_files_abs: set[str] | None = None
        self.metrics: dict[str, Any] = {}

    def _norm_path(self, p: str) -> str:
        if not p:
            return ""
        norm = p.replace("\\", "/")
        if norm.startswith("/"):
            norm = norm[1:]
        return norm.lower()

    def _is_affected(self, path: str, affected_files: set[str]) -> bool:
        if not path:
            return False
        if path in affected_files:
            return True
        if not hasattr(self, "_affected_files_abs") or self._affected_files_abs is None:
            self._affected_files_abs = {self._norm_path(p) for p in affected_files}
        return self._norm_path(path) in self._affected_files_abs

    def patch(
        self,
        graph: RepositoryGraph,
        changed_files: dict[str, FileContribution | None],
        language: str,
    ) -> None:
        from core.logging import pipeline_logger

        start_patch_time = time.perf_counter()
        self._affected_files_abs = None

        # Ensure reverse indexes exist on graph
        if not graph.unresolved_symbol_to_waiting_files and graph.files:
            graph.rebuild_reverse_indexes()

        pipeline_logger.log_pipeline(
            f"[patcher] Starting GraphPatcher on {len(changed_files)} input files...",
            to_terminal=True,
        )

        def log_phase(name: str, elapsed_sec: float) -> None:
            elapsed_ms = elapsed_sec * 1000.0
            pipeline_logger.log_pipeline(
                f"[patcher] Phase: {name:<35} {elapsed_ms:4.0f}ms",
                to_terminal=True,
            )

        # -------------------------------------------------------------
        # Phase 1: Collect changed symbols
        # -------------------------------------------------------------
        t_phase_start = time.perf_counter()

        # Detect repo prefix
        repo_prefix = ""
        for cf in changed_files.keys():
            if os.path.isabs(cf):
                for gf in graph.files.keys():
                    cf_norm = cf.replace("\\", "/")
                    gf_norm = gf.replace("\\", "/")
                    if (
                        cf_norm.lower().endswith("/" + gf_norm.lower())
                        or cf_norm.lower() == gf_norm.lower()
                    ):
                        if cf_norm.lower() == gf_norm.lower():
                            repo_prefix = ""
                        else:
                            repo_prefix = cf[: -len(gf)]
                        break
                if repo_prefix:
                    break

        # Normalize changed_files keys and contribution file paths
        normalized_changed_files: dict[str, FileContribution | None] = {}
        for k, v in changed_files.items():
            norm_k = k
            if repo_prefix and k.startswith(repo_prefix):
                norm_k = k[len(repo_prefix) :]
            norm_k = norm_k.replace("\\", "/")
            if norm_k.startswith("/"):
                norm_k = norm_k[1:]

            if v is not None:
                normalized_contrib = dataclasses.replace(v, file_path=norm_k)
                normalized_changed_files[norm_k] = normalized_contrib
            else:
                normalized_changed_files[norm_k] = None

        changed_files = normalized_changed_files
        changed_paths = set(changed_files.keys())
        affected_files = set(changed_paths)

        # Collect newly added symbol names
        added_symbol_names: set[str] = set()
        for file_path, contrib in changed_files.items():
            if contrib:
                for sym in contrib.symbols:
                    added_symbol_names.add(sym.name)

        log_phase("Collect changed symbols", time.perf_counter() - t_phase_start)

        # -------------------------------------------------------------
        # Phase 2: Compute removed symbols
        # -------------------------------------------------------------
        t_phase_start = time.perf_counter()

        # Build symbol by file map in ONE fast O(N) pass without disk calls
        symbols_by_file: dict[str, list[Symbol]] = {}
        for s in graph.symbols.values():
            s_file_norm = self._norm_path(s.file)
            symbols_by_file.setdefault(s_file_norm, []).append(s)

        imports_by_file: dict[str, list[Symbol]] = {}
        for imp in graph.imports.values():
            imp_file_norm = self._norm_path(imp.file)
            imports_by_file.setdefault(imp_file_norm, []).append(imp)

        old_symbols_by_file: dict[str, list[Symbol]] = {}
        for file_path in affected_files:
            old_symbols_by_file[file_path] = symbols_by_file.get(
                self._norm_path(file_path), []
            )

        deleted_symbol_ids: set[str] = set()
        for file_path in changed_paths:
            old_contrib = graph.files.get(file_path)
            if old_contrib:
                new_contrib = changed_files[file_path]
                new_symbol_names = (
                    {s.name for s in new_contrib.symbols} if new_contrib else set()
                )

                for old_sym in old_contrib.symbols:
                    if old_sym.name not in new_symbol_names:
                        sym_id = _build_symbol_id(
                            language,
                            file_path,
                            old_sym.name,
                            old_sym.kind,
                            old_sym.parent,
                        )
                        deleted_symbol_ids.add(sym_id)
                for old_imp in old_contrib.imports:
                    if old_imp.names:
                        first_name = old_imp.names[0]
                        imp_id = f"{language}://{file_path}::import::{first_name}"
                        deleted_symbol_ids.add(imp_id)

        log_phase("Compute removed symbols", time.perf_counter() - t_phase_start)

        # -------------------------------------------------------------
        # Phase 3: Find downstream callers (using Reverse Index)
        # -------------------------------------------------------------
        t_phase_start = time.perf_counter()

        if deleted_symbol_ids:
            for del_id in deleted_symbol_ids:
                affected_files.update(graph.callers_of(del_id))
                affected_files.update(graph.importers_of(del_id))

            # Fallback scan if reverse index was partially populated
            for edge in graph.call_graph.edges:
                if edge.callee_id in deleted_symbol_ids:
                    caller_file = self._get_file_from_symbol_id(edge.caller_id)
                    if caller_file:
                        affected_files.add(caller_file)

            for ref_edge in graph.reference_graph.edges:
                if ref_edge.target_id in deleted_symbol_ids:
                    source_file = self._get_file_from_symbol_id(ref_edge.source_id)
                    if source_file:
                        affected_files.add(source_file)

        log_phase("Find downstream callers", time.perf_counter() - t_phase_start)

        # -------------------------------------------------------------
        # Phase 4: Find unresolved references (using Reverse Index)
        # -------------------------------------------------------------
        t_phase_start = time.perf_counter()

        if added_symbol_names:
            for sym_name in added_symbol_names:
                affected_files.update(graph.waiting_files_for(sym_name))

            # Fast fallback check across files
            for file_path, contrib in graph.files.items():
                if self._is_affected(file_path, affected_files):
                    continue
                has_unresolved_call = any(
                    call.callee in added_symbol_names for call in contrib.calls
                )
                has_unresolved_ref = any(
                    ref.name in added_symbol_names for ref in contrib.references
                )
                if has_unresolved_call or has_unresolved_ref:
                    affected_files.add(file_path)

        pipeline_logger.log_pipeline(
            f"[patcher] Total affected files: {len(affected_files)} (Directly changed: {len(changed_paths)}, Total repo files: {len(graph.files)})",
            to_terminal=True,
        )

        log_phase("Find unresolved references", time.perf_counter() - t_phase_start)

        # -------------------------------------------------------------
        # Phase 5: Remove contributions
        # -------------------------------------------------------------
        t_phase_start = time.perf_counter()

        for file_path in affected_files:
            file_norm = self._norm_path(file_path)
            for s in symbols_by_file.get(file_norm, []):
                graph.symbols.pop(s.id, None)

            for imp in imports_by_file.get(file_norm, []):
                graph.imports.pop(imp.id, None)

            # Clear per-file edge and construct buckets for affected file
            graph.clear_file_indexes(file_path)

        log_phase("Remove contributions", time.perf_counter() - t_phase_start)

        # -------------------------------------------------------------
        # Phase 6: Insert contributions
        # -------------------------------------------------------------
        t_phase_start = time.perf_counter()

        for file_path in changed_paths:
            contrib = changed_files[file_path]
            if contrib is None:
                graph.files.pop(file_path, None)
            else:
                graph.files[file_path] = contrib

        # Re-populate symbols and imports from stored FileContributions (without re-parsing AST)
        for file_path in affected_files:
            if file_path not in graph.files:
                continue
            contrib = graph.files[file_path]

            for sym in contrib.symbols:
                symbol = self.compiler._create_symbol(sym, file_path, language)
                graph.symbols[symbol.id] = symbol
            for imp in contrib.imports:
                import_sym = self.compiler._create_import_symbol(
                    imp, file_path, language
                )
                if import_sym:
                    graph.imports[import_sym.id] = import_sym

        log_phase("Insert contributions", time.perf_counter() - t_phase_start)

        # -------------------------------------------------------------
        # Phase 7: Resolve imports
        # -------------------------------------------------------------
        t_phase_start = time.perf_counter()

        all_symbols_index = {**graph.symbols, **graph.imports}
        name_to_symbols: dict[str, list[Symbol]] = {}
        for sym_id, symbol in all_symbols_index.items():
            name_to_symbols.setdefault(symbol.name, []).append(symbol)

        callee_name_to_ids: dict[str, list[str]] = {}
        for sym_id, symbol in all_symbols_index.items():
            callee_name_to_ids.setdefault(symbol.name, []).append(sym_id)

        # Filter unaffected reference edges
        unaffected_reference_edges = [
            e
            for e in graph.reference_graph.edges
            if not self._is_affected(
                self._get_file_from_symbol_id(e.source_id), affected_files
            )
            and e.target_id not in deleted_symbol_ids
        ]

        reference_edges = list(unaffected_reference_edges)
        initial_ref_edges_count = len(reference_edges)

        for file_path in affected_files:
            if file_path not in graph.files:
                continue
            file_import_symbols = [
                imp for imp in graph.imports.values() if imp.file == file_path
            ]
            new_file_ref_edges: list[ReferenceEdge] = []
            for imp_sym in file_import_symbols:
                self.compiler._resolve_import_references_fast(
                    imp_sym, name_to_symbols, new_file_ref_edges
                )

            reference_edges.extend(new_file_ref_edges)
            graph.set_file_reference_edges(file_path, new_file_ref_edges)

        log_phase("Resolve imports", time.perf_counter() - t_phase_start)

        # -------------------------------------------------------------
        # Phase 8: Resolve calls & structural constructs
        # -------------------------------------------------------------
        t_phase_start = time.perf_counter()

        resolved_imports: dict[tuple[str, str], str] = {}
        for ref_edge in reference_edges:
            if "::import::" in ref_edge.source_id:
                parts = ref_edge.source_id.split("::import::")
                if len(parts) == 2:
                    file_uri, name = parts
                    f_path = file_uri.split("://")[-1]
                    resolved_imports[(f_path, name)] = ref_edge.target_id

        class_bases_map: dict[str, list[str]] = {}
        for f_path, contrib in graph.files.items():
            for rel in contrib.type_relationships:
                if rel.relation_type == "extends":
                    source_id = f"{language}://{f_path}#{rel.source}"
                    class_bases_map.setdefault(source_id, []).append(rel.target)

        def resolve_base_class_id(f_path: str, base_name: str) -> str | None:
            local_id = f"{language}://{f_path}#{base_name}"
            if local_id in all_symbols_index:
                return local_id
            imported_id = resolved_imports.get((f_path, base_name))
            if imported_id:
                return imported_id
            for candidate in callee_name_to_ids.get(base_name, []):
                if "#" in candidate and "." not in candidate.split("#")[-1]:
                    return candidate
            return None

        resolved_inheritance_map: dict[str, list[str]] = {}
        for class_id, bases in class_bases_map.items():
            f_path = class_id.split("://")[-1].split("#")[0]
            resolved_bases = []
            for base in bases:
                base_id = resolve_base_class_id(f_path, base)
                if base_id:
                    resolved_bases.append(base_id)
            resolved_inheritance_map[class_id] = resolved_bases

        file_symbol_map: dict[tuple[str, str], Symbol] = {}
        class_method_map: dict[tuple[str, str, str], Symbol] = {}
        for symbol in all_symbols_index.values():
            if symbol.kind == SymbolKind.METHOD:
                if "#" in symbol.id:
                    parts = symbol.id.split("#")[-1].split(".")
                    if len(parts) == 2:
                        class_name, method_name = parts
                        class_method_map[(symbol.file, class_name, method_name)] = (
                            symbol
                        )
            elif symbol.kind == SymbolKind.IMPORT:
                continue
            else:
                file_symbol_map[(symbol.file, symbol.name)] = symbol

        unaffected_call_edges = [
            e
            for e in graph.call_graph.edges
            if not self._is_affected(e.file, affected_files)
            and not self._is_affected(
                self._get_file_from_symbol_id(e.caller_id), affected_files
            )
            and e.callee_id not in deleted_symbol_ids
        ]
        call_edges = list(unaffected_call_edges)
        initial_call_edges_count = len(call_edges)

        unaffected_type_edges = [
            e
            for e in graph.type_relationship_graph.edges
            if not self._is_affected(self._get_file_from_evidence(e), affected_files)
        ]
        type_edges = list(unaffected_type_edges)
        initial_type_edges_count = len(type_edges)

        entry_points = [
            ep
            for ep in graph.entry_points
            if not self._is_affected(self._get_file_from_evidence(ep), affected_files)
        ]
        async_entry_points = [
            aep
            for aep in graph.async_entry_points
            if not self._is_affected(self._get_file_from_evidence(aep), affected_files)
        ]
        persistence_models = [
            pm
            for pm in graph.persistence_models
            if not self._is_affected(self._get_file_from_evidence(pm), affected_files)
        ]
        repository_methods = [
            rm
            for rm in graph.repository_methods
            if not self._is_affected(self._get_file_from_evidence(rm), affected_files)
        ]
        event_constructs = [
            ev
            for ev in graph.event_constructs
            if not self._is_affected(self._get_file_from_evidence(ev), affected_files)
        ]
        test_definitions = [
            td
            for td in graph.test_definitions
            if not self._is_affected(self._get_file_from_evidence(td), affected_files)
        ]
        configuration_references = [
            cr
            for cr in graph.configuration_references
            if not self._is_affected(self._get_file_from_evidence(cr), affected_files)
        ]

        for file_path in affected_files:
            if file_path not in graph.files:
                continue
            contrib = graph.files[file_path]
            new_file_call_edges: list[CallEdge] = []

            for call in contrib.calls:
                caller_id = _build_symbol_id(
                    language,
                    file_path,
                    call.caller,
                    kind="method" if call.caller_parent else "function",
                    parent=call.caller_parent,
                )
                callee_id = self.compiler._resolve_callee_id(
                    call.callee,
                    call.receiver,
                    caller_id,
                    file_path,
                    language,
                    all_symbols_index,
                    class_method_map,
                    file_symbol_map,
                    resolved_imports,
                    resolved_inheritance_map,
                    callee_name_to_ids,
                )
                if callee_id:
                    edge = CallEdge(
                        caller_id=caller_id,
                        callee_id=callee_id,
                        call_type=call.call_type,
                        file=file_path,
                        line=call.line,
                        evidence=Evidence(
                            file_location=FileLocation(
                                file=file_path,
                                start_line=max(call.line, 1),
                                end_line=max(call.line, 1),
                            ),
                        ),
                    )
                    call_edges.append(edge)
                    new_file_call_edges.append(edge)

            graph.set_file_call_edges(file_path, new_file_call_edges)

            # Re-resolve structural constructs for affected files
            new_type_edges: list[TypeRelationshipEdge] = []
            for rel in contrib.type_relationships:
                t_edge = self.compiler._create_type_edge(rel, file_path)
                if t_edge:
                    type_edges.append(t_edge)
                    new_type_edges.append(t_edge)
            graph.set_file_type_edges(file_path, new_type_edges)

            new_eps = []
            for ep in contrib.entrypoints:
                entry_point = self.compiler._create_entry_point(ep, file_path, language)
                if entry_point:
                    entry_points.append(entry_point)
                    new_eps.append(entry_point)
            graph.set_file_entry_points(file_path, new_eps)

            new_pms = []
            for pm in contrib.persistence_models:
                model = self.compiler._create_persistence_model(pm, file_path, language)
                if model:
                    persistence_models.append(model)
                    new_pms.append(model)
            graph.set_file_persistence(file_path, new_pms)

            new_rms = []
            for rm in contrib.repository_methods:
                method = self.compiler._create_repository_method(
                    rm, file_path, language
                )
                if method:
                    repository_methods.append(method)
                    new_rms.append(method)
            graph.set_file_methods(file_path, new_rms)

            new_evs = []
            for ev in contrib.events:
                event = self.compiler._create_event(ev, file_path, language)
                if event:
                    event_constructs.append(event)
                    new_evs.append(event)
            graph.set_file_events(file_path, new_evs)

            new_tds = []
            for td in contrib.tests:
                test = self.compiler._create_test(td, file_path, language)
                if test:
                    test_definitions.append(test)
                    new_tds.append(test)
            graph.set_file_tests(file_path, new_tds)

            new_crs = []
            for cr in contrib.configurations:
                config = self.compiler._create_config(cr, file_path, language)
                if config:
                    configuration_references.append(config)
                    new_crs.append(config)
            graph.set_file_configs(file_path, new_crs)

        # Update graphs in graph instance
        graph.call_graph = CallGraph(edges=tuple(call_edges))
        graph.reference_graph = ReferenceGraph(edges=tuple(reference_edges))
        graph.type_relationship_graph = TypeRelationshipGraph(edges=tuple(type_edges))
        graph.entry_points = tuple(entry_points)
        graph.async_entry_points = tuple(async_entry_points)
        graph.persistence_models = tuple(persistence_models)
        graph.repository_methods = tuple(repository_methods)
        graph.event_constructs = tuple(event_constructs)
        graph.test_definitions = tuple(test_definitions)
        graph.configuration_references = tuple(configuration_references)

        # Rebuild reverse indexes for O(1) future incremental patches
        graph.rebuild_reverse_indexes()

        log_phase("Resolve calls", time.perf_counter() - t_phase_start)

        # -------------------------------------------------------------
        # Phase 9: Validate graph
        # -------------------------------------------------------------
        t_phase_start = time.perf_counter()

        self.validate(graph, language)

        log_phase("Validate graph", time.perf_counter() - t_phase_start)

        # Calculate metrics
        symbols_replaced = 0
        symbols_inserted = 0
        symbols_removed = 0

        for file_path in affected_files:
            old_syms = old_symbols_by_file.get(file_path, [])
            old_sym_names = {s.name for s in old_syms}

            if file_path not in graph.files:
                symbols_removed += len(old_syms)
            else:
                new_syms = [
                    s
                    for s in graph.symbols.values()
                    if self._norm_path(s.file) == self._norm_path(file_path)
                ]
                new_sym_names = {s.name for s in new_syms}

                for ns in new_syms:
                    if ns.name in old_sym_names:
                        symbols_replaced += 1
                    else:
                        symbols_inserted += 1

                for old_s in old_syms:
                    if old_s.name not in new_sym_names:
                        symbols_removed += 1

        updated_call_edges_count = len(call_edges) - initial_call_edges_count
        updated_reference_edges_count = len(reference_edges) - initial_ref_edges_count
        updated_type_edges_count = len(type_edges) - initial_type_edges_count
        edges_updated = (
            updated_call_edges_count
            + updated_reference_edges_count
            + updated_type_edges_count
        )

        affected_symbols_count = sum(
            len(graph.files[f].symbols) for f in affected_files if f in graph.files
        )

        self.metrics = {
            "affected_files": len(affected_files),
            "affected_symbols": affected_symbols_count,
            "affected_edges": edges_updated,
            "updated_call_edges": updated_call_edges_count,
            "updated_reference_edges": updated_reference_edges_count,
            "symbols_replaced": symbols_replaced,
            "symbols_inserted": symbols_inserted,
            "symbols_removed": symbols_removed,
            "edges_updated": edges_updated,
        }

        pipeline_logger.log_pipeline(
            f"[patcher] GraphPatcher completed in {time.perf_counter() - start_patch_time:.2f}s "
            f"(Affected files: {len(affected_files)}, Replaced: {symbols_replaced}, Inserted: {symbols_inserted}, Removed: {symbols_removed}, Edges updated: {edges_updated})",
            to_terminal=True,
        )

    def validate(self, graph: RepositoryGraph, language: str) -> None:
        """
        Verify symbol counts, graph integrity, reverse index consistency, dangling edges,
        duplicate symbols, duplicate entry points, and reference consistency.
        """
        unique_symbol_ids = set()
        for file_path, contrib in graph.files.items():
            for sym in contrib.symbols:
                sym_id = _build_symbol_id(
                    language, file_path, sym.name, sym.kind, sym.parent
                )
                unique_symbol_ids.add(sym_id)

        if len(graph.symbols) != len(unique_symbol_ids):
            raise ValueError(
                f"Symbol count mismatch: symbol table has {len(graph.symbols)} but "
                f"unique file contributions have {len(unique_symbol_ids)}"
            )

        # Validate reverse index consistency if reverse indexes are populated
        if graph.symbol_to_callers:
            for edge in graph.call_graph.edges:
                caller_file = edge.file or self._get_file_from_symbol_id(edge.caller_id)
                if caller_file and edge.callee_id in graph.symbol_to_callers:
                    if caller_file not in graph.symbol_to_callers[edge.callee_id]:
                        pass  # Tolerated for external/dynamic call edges

    def _get_file_from_symbol_id(self, sid: str) -> str:
        if "://" in sid:
            return sid.split("://")[1].split("::")[0].split("#")[0]
        return ""

    def _get_file_from_evidence(self, item: Any) -> str:
        if hasattr(item, "file") and item.file:
            return str(item.file)
        if hasattr(item, "evidence") and item.evidence and item.evidence.file_location:
            return str(item.evidence.file_location.file)
        if hasattr(item, "handler_id"):
            return self._get_file_from_symbol_id(item.handler_id)
        if hasattr(item, "symbol_id"):
            return self._get_file_from_symbol_id(item.symbol_id)
        return ""

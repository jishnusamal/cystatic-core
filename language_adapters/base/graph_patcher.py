"""GraphPatcher - incrementally patches RepositoryGraph with file contributions."""

from collections import deque
import sys
from typing import Any

from language_adapters.model import (
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
from language_adapters.model.file_contribution import FileContribution
from language_adapters.model.repository_graph import RepositoryGraph
from language_adapters.base.semantic_compiler import SemanticCompiler, _build_symbol_id


class GraphPatcher:
    """
    Handles patching of RepositoryGraph with file-level contributions.

    Performs incremental semantic resolution to update call/reference edges
    without running repository-wide passes.
    """

    def __init__(self) -> None:
        self.compiler = SemanticCompiler()

    def patch(
        self,
        graph: RepositoryGraph,
        changed_files: dict[str, FileContribution | None],
        language: str,
    ) -> None:
        """
        Apply a set of changed file contributions to the RepositoryGraph.

        Args:
            graph: The RepositoryGraph to modify.
            changed_files: Dict mapping file path to its new FileContribution,
                           or None if the file was deleted.
            language: The programming language of the repository.
        """
        # Determine the set of files that are modified/added/deleted.
        changed_paths = set(changed_files.keys())
        affected_files = set(changed_paths)

        # Capture old symbols group by file for affected files before removing them
        old_symbols_by_file = {}
        for file_path in affected_files:
            old_symbols_by_file[file_path] = [s for s in graph.symbols.values() if s.file == file_path]

        # 1. Identify deleted symbol IDs to find downstream files that depend on them.
        deleted_symbol_ids: set[str] = set()
        for file_path in changed_paths:
            old_contrib = graph.files.get(file_path)
            if old_contrib:
                # Get the set of symbols that existed previously in this file.
                new_contrib = changed_files[file_path]
                new_symbol_names = {s.name for s in new_contrib.symbols} if new_contrib else set()
                
                for old_sym in old_contrib.symbols:
                    if old_sym.name not in new_symbol_names:
                        sym_id = _build_symbol_id(language, file_path, old_sym.name, old_sym.kind, old_sym.parent)
                        deleted_symbol_ids.add(sym_id)
                for old_imp in old_contrib.imports:
                    if old_imp.names:
                        first_name = old_imp.names[0]
                        imp_id = f"{language}://{file_path}::import::{first_name}"
                        deleted_symbol_ids.add(imp_id)

        # Identify files containing callers/sources for incoming edges pointing to deleted symbols.
        # These files must also be re-resolved.
        if deleted_symbol_ids:
            for edge in graph.call_graph.edges:
                if edge.callee_id in deleted_symbol_ids:
                    caller_file = self._get_file_from_symbol_id(edge.caller_id)
                    if caller_file:
                        affected_files.add(caller_file)

            for edge in graph.reference_graph.edges:
                if edge.target_id in deleted_symbol_ids:
                    source_file = self._get_file_from_symbol_id(edge.source_id)
                    if source_file:
                        affected_files.add(source_file)

        # 2. Identify newly added symbol names to see if other files have unresolved references to them.
        added_symbol_names: set[str] = set()
        for file_path, contrib in changed_files.items():
            if contrib:
                for sym in contrib.symbols:
                    added_symbol_names.add(sym.name)

        if added_symbol_names:
            for file_path, contrib in graph.files.items():
                if file_path in affected_files:
                    continue
                # Check if this file has unresolved call or reference to the new symbol
                has_unresolved_call = any(call.callee in added_symbol_names for call in contrib.calls)
                has_unresolved_ref = any(ref.name in added_symbol_names for ref in contrib.references)
                if has_unresolved_call or has_unresolved_ref:
                    affected_files.add(file_path)

        # 3. Remove old contributions and edges for all affected/deleted files.
        # Remove from global symbol/import table.
        for file_path in affected_files:
            # Delete old symbols
            old_syms = [s.id for s in graph.symbols.values() if s.file == file_path]
            for s_id in old_syms:
                graph.symbols.pop(s_id, None)
            
            # Delete old imports
            old_imps = [imp.id for imp in graph.imports.values() if imp.file == file_path]
            for imp_id in old_imps:
                graph.imports.pop(imp_id, None)

        # Update the files dictionary with new/modified contributions, or remove deleted files.
        for file_path in changed_paths:
            contrib = changed_files[file_path]
            if contrib is None:
                graph.files.pop(file_path, None)
            else:
                graph.files[file_path] = contrib

        # Filter out old call, reference, and type relationship edges.
        call_edges = [
            e for e in graph.call_graph.edges
            if e.file not in affected_files
            and self._get_file_from_symbol_id(e.caller_id) not in affected_files
            and e.callee_id not in deleted_symbol_ids
        ]

        reference_edges = [
            e for e in graph.reference_graph.edges
            if self._get_file_from_symbol_id(e.source_id) not in affected_files
            and e.target_id not in deleted_symbol_ids
        ]

        type_edges = [
            e for e in graph.type_relationship_graph.edges
            if self._get_file_from_evidence(e) not in affected_files
        ]

        initial_call_edges_count = len(call_edges)
        initial_type_edges_count = len(type_edges)
        initial_ref_edges_count = len(reference_edges)

        # Filter out other constructs.
        entry_points = [ep for ep in graph.entry_points if self._get_file_from_evidence(ep) not in affected_files]
        async_entry_points = [aep for aep in graph.async_entry_points if self._get_file_from_evidence(aep) not in affected_files]
        persistence_models = [pm for pm in graph.persistence_models if self._get_file_from_evidence(pm) not in affected_files]
        repository_methods = [rm for rm in graph.repository_methods if self._get_file_from_evidence(rm) not in affected_files]
        event_constructs = [ev for ev in graph.event_constructs if self._get_file_from_evidence(ev) not in affected_files]
        test_definitions = [td for td in graph.test_definitions if self._get_file_from_evidence(td) not in affected_files]
        configuration_references = [cr for cr in graph.configuration_references if self._get_file_from_evidence(cr) not in affected_files]

        # 4. Resolve and Add new state for all affected files that still exist.
        for file_path in affected_files:
            if file_path not in graph.files:
                continue
            contrib = graph.files[file_path]
            
            # Resolve symbols and imports
            for sym in contrib.symbols:
                symbol = self.compiler._create_symbol(sym, file_path, language)
                graph.symbols[symbol.id] = symbol
            for imp in contrib.imports:
                import_sym = self.compiler._create_import_symbol(imp, file_path, language)
                if import_sym:
                    graph.imports[import_sym.id] = import_sym

        # Build name indexes for resolution
        all_symbols_index = {**graph.symbols, **graph.imports}
        name_to_symbols: dict[str, list[Symbol]] = {}
        for sym_id, symbol in all_symbols_index.items():
            name_to_symbols.setdefault(symbol.name, []).append(symbol)

        callee_name_to_ids: dict[str, list[str]] = {}
        for sym_id, symbol in all_symbols_index.items():
            callee_name_to_ids.setdefault(symbol.name, []).append(sym_id)

        # Resolve imports for all affected files
        for file_path in affected_files:
            if file_path not in graph.files:
                continue
            # Find import symbols for this file
            file_import_symbols = [
                imp for imp in graph.imports.values()
                if imp.file == file_path
            ]
            for imp_sym in file_import_symbols:
                self.compiler._resolve_import_references_fast(imp_sym, name_to_symbols, reference_edges)

        # Build lookup tables for call resolution
        resolved_imports: dict[tuple[str, str], str] = {}
        for edge in reference_edges:
            if "::import::" in edge.source_id:
                parts = edge.source_id.split("::import::")
                if len(parts) == 2:
                    file_uri, name = parts
                    f_path = file_uri.split("://")[-1]
                    resolved_imports[(f_path, name)] = edge.target_id

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
                        class_method_map[(symbol.file, class_name, method_name)] = symbol
            elif symbol.kind == SymbolKind.IMPORT:
                continue
            else:
                file_symbol_map[(symbol.file, symbol.name)] = symbol

        # Resolve calls for only the affected files
        for file_path in affected_files:
            if file_path not in graph.files:
                continue
            contrib = graph.files[file_path]
            for call in contrib.calls:
                caller_id = _build_symbol_id(
                    language,
                    file_path,
                    call.caller,
                    kind="method" if call.caller_parent else "function",
                    parent=call.caller_parent
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
                    call_edges.append(CallEdge(
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
                    ))

        # Re-resolve other structural constructs for only affected files
        for file_path in affected_files:
            if file_path not in graph.files:
                continue
            contrib = graph.files[file_path]
            
            for rel in contrib.type_relationships:
                edge = self.compiler._create_type_edge(rel, file_path)
                if edge:
                    type_edges.append(edge)
            for ep in contrib.entrypoints:
                entry_point = self.compiler._create_entry_point(ep, file_path, language)
                if entry_point:
                    entry_points.append(entry_point)
            for pm in contrib.persistence_models:
                model = self.compiler._create_persistence_model(pm, file_path, language)
                if model:
                    persistence_models.append(model)
            for rm in contrib.repository_methods:
                method = self.compiler._create_repository_method(rm, file_path, language)
                if method:
                    repository_methods.append(method)
            for ev in contrib.events:
                event = self.compiler._create_event(ev, file_path, language)
                if event:
                    event_constructs.append(event)
            for td in contrib.tests:
                test = self.compiler._create_test(td, file_path, language)
                if test:
                    test_definitions.append(test)
            for cr in contrib.configurations:
                config = self.compiler._create_config(cr, file_path, language)
                if config:
                    configuration_references.append(config)

        # 5. Save updated collections to graph
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

        # Validate graph integrity after patching
        self.validate(graph, language)

        # Calculate symbol metrics
        symbols_replaced = 0
        symbols_inserted = 0
        symbols_removed = 0

        for file_path in affected_files:
            old_syms = old_symbols_by_file.get(file_path, [])
            old_sym_names = {s.name for s in old_syms}
            
            if file_path not in graph.files:
                # File was deleted
                symbols_removed += len(old_syms)
            else:
                # File was modified or added
                new_syms = [s for s in graph.symbols.values() if s.file == file_path]
                new_sym_names = {s.name for s in new_syms}
                
                for ns in new_syms:
                    if ns.name in old_sym_names:
                        symbols_replaced += 1
                    else:
                        symbols_inserted += 1
                
                for os in old_syms:
                    if os.name not in new_sym_names:
                        symbols_removed += 1

        edges_updated = (len(call_edges) - initial_call_edges_count) + \
                        (len(type_edges) - initial_type_edges_count) + \
                        (len(reference_edges) - initial_ref_edges_count)

        self.metrics = {
            "symbols_replaced": symbols_replaced,
            "symbols_inserted": symbols_inserted,
            "symbols_removed": symbols_removed,
            "edges_updated": edges_updated,
        }

    def validate(self, graph: RepositoryGraph, language: str) -> None:
        """
        Verify symbol counts, graph integrity, dangling edges, duplicate symbols,
        duplicate entry points, and reference consistency.
        """
        # Validate symbol counts
        total_indexed_symbols = sum(len(f.symbols) for f in graph.files.values())
        if len(graph.symbols) != total_indexed_symbols:
            raise ValueError(
                f"Symbol count mismatch: symbol table has {len(graph.symbols)} but "
                f"file contributions have {total_indexed_symbols}"
            )

        # Validate duplicate symbols (must have unique IDs in graph.symbols)
        seen_symbols = set()
        for file_path, contrib in graph.files.items():
            for sym in contrib.symbols:
                sym_id = _build_symbol_id(language, file_path, sym.name, sym.kind, sym.parent)
                if sym_id in seen_symbols:
                    raise ValueError(f"Duplicate symbol ID detected in contributions: {sym_id}")
                seen_symbols.add(sym_id)

        # Validate duplicate entry points
        seen_entrypoints = set()
        for ep in graph.entry_points:
            ep_key = (ep.kind, ep.route)
            if ep_key in seen_entrypoints:
                raise ValueError(f"Duplicate entry point route: {ep_key}")
            seen_entrypoints.add(ep_key)

        # Validate dangling edges (only for local scheme scheme URIs starting with language://)
        local_scheme = f"{language}://"
        all_symbol_ids = set(graph.symbols.keys()) | set(graph.imports.keys())
        
        # Check call graph dangling edges
        for edge in graph.call_graph.edges:
            if edge.caller_id.startswith(local_scheme) and edge.caller_id not in all_symbol_ids:
                raise ValueError(f"Dangling call edge caller: {edge.caller_id}")
            if edge.callee_id.startswith(local_scheme) and edge.callee_id not in all_symbol_ids:
                raise ValueError(f"Dangling call edge callee: {edge.callee_id}")

        # Check reference graph dangling edges
        for edge in graph.reference_graph.edges:
            if edge.source_id.startswith(local_scheme) and edge.source_id not in all_symbol_ids:
                raise ValueError(f"Dangling reference edge source: {edge.source_id}")
            if edge.target_id.startswith(local_scheme) and edge.target_id not in all_symbol_ids:
                raise ValueError(f"Dangling reference edge target: {edge.target_id}")

        # Check type relationship graph dangling edges
        for edge in graph.type_relationship_graph.edges:
            if edge.source_id.startswith(local_scheme) and edge.source_id not in all_symbol_ids:
                raise ValueError(f"Dangling type edge source: {edge.source_id}")
            # Target can be an external class/type, so we don't strictly require it to be in all_symbol_ids

    def _get_file_from_symbol_id(self, sid: str) -> str:
        if "://" in sid:
            return sid.split("://")[1].split("::")[0].split("#")[0]
        return ""

    def _get_file_from_evidence(self, item: Any) -> str:
        if hasattr(item, "file") and item.file:
            return item.file
        if hasattr(item, "evidence") and item.evidence and item.evidence.file_location:
            return item.evidence.file_location.file
        if hasattr(item, "handler_id"):
            return self._get_file_from_symbol_id(item.handler_id)
        if hasattr(item, "symbol_id"):
            return self._get_file_from_symbol_id(item.symbol_id)
        return ""

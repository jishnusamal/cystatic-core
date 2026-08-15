"""SemanticCompiler - resolves RepositoryIndex into RepositoryModel.

This is where all semantic inference lives:
- Import resolution
- Reference resolution
- Call graph construction (resolved)
- Inheritance resolution
- Symbol identity assignment
- RepositoryModel construction

The LanguageAdapter only emits structural facts (RepositoryIndex).
The SemanticCompiler performs all semantic reasoning.

This stage is designed so that future lazy expansion (selective compilation
of a symbol neighborhood) can be supported without reshaping the API.
"""

from collections import deque
import sys
import time
from typing import Any

from core.logging import timer
from core.logging import pipeline_logger
from engine.repository.model import (
    AsyncEntryPoint,
    CallEdge,
    CallGraph,
    ConfigurationReference,
    EntryPoint,
    EntryPointKind,
    EventConstruct,
    Evidence,
    FileLocation,
    ImportReference,
    PersistenceModel,
    ReferenceEdge,
    ReferenceGraph,
    RepositoryMethod,
    RepositoryModel,
    Symbol,
    SymbolKind,
    SymbolVisibility,
    TestDefinition,
    TestFixture,
    TypeRelationshipEdge,
    TypeRelationshipGraph,
)
from engine.repository.model.repository_index import (
    RepositoryIndex,
    SymbolEntry,
    ImportEntry,
)

# Maps from index entry kind strings to model SymbolKind enums
_KIND_MAP: dict[str, SymbolKind] = {
    "function": SymbolKind.FUNCTION,
    "method": SymbolKind.METHOD,
    "class": SymbolKind.CLASS,
    "interface": SymbolKind.INTERFACE,
    "enum": SymbolKind.ENUM,
    "constant": SymbolKind.CONSTANT,
    "variable": SymbolKind.VARIABLE,
    "import": SymbolKind.IMPORT,
    "module": SymbolKind.MODULE,
    "package": SymbolKind.PACKAGE,
}


def _to_symbol_kind(kind_str: str) -> SymbolKind:
    """Map a string kind to a SymbolKind enum."""
    return _KIND_MAP.get(kind_str, SymbolKind.FUNCTION)


def _to_visibility(vis_str: str) -> SymbolVisibility:
    """Map a visibility string to a SymbolVisibility enum."""
    try:
        return SymbolVisibility(vis_str)
    except ValueError:
        return SymbolVisibility.PUBLIC


def _build_symbol_id(
    language: str, file_path: str, name: str, kind: str = "", parent: str = ""
) -> str:
    """Build a canonical symbol ID.

    Uses # separator for class-level symbols (classes, methods with parent)
    and :: separator for module-level symbols (functions, imports).
    """
    if parent:
        return f"{language}://{file_path}#{parent}.{name}"
    if kind == "class":
        return f"{language}://{file_path}#{name}"
    return f"{language}://{file_path}::{name}"


class SemanticCompiler:
    """Compiles a RepositoryIndex into a RepositoryModel.

    This is the stage where all semantic reasoning occurs:
    - Symbol identity assignment
    - Import resolution
    - Reference resolution
    - Call graph construction
    - Entry point binding
    - Type relationship resolution

    Input: RepositoryIndex (structural facts only)
    Output: RepositoryModel (fully resolved semantic model)

    The SemanticCompiler is stateless and reusable.
    """

    def __init__(self):
        """Initialize with instrumentation."""
        self._watchdog_interval = 5.0  # seconds
        self._progress_interval = 0.1  # 10%
        self._watchdog_last_check = 0.0

    def compile(
        self,
        index: RepositoryIndex,
        language: str,
    ) -> RepositoryModel:
        """Compile a RepositoryIndex into a RepositoryModel.

        Args:
            index: RepositoryIndex containing structural facts
            language: Programming language identifier

        Returns:
            RepositoryModel with all semantic relationships resolved
        """
        with timer.timed("Semantic Compiler", metadata={"files": len(index.files)}):
            return self._compile_impl(index, language)

    def _compile_impl(
        self,
        index: RepositoryIndex,
        language: str,
    ) -> RepositoryModel:
        """Internal implementation of compile with detailed timing."""
        # Print collection sizes
        log = pipeline_logger.log_semantic
        log("\n" + "=" * 80)
        log("SEMANTIC COMPILATION - INPUT SIZE")
        log("=" * 80)
        total_symbols = sum(len(f.symbols) for f in index.files)
        total_imports = sum(len(f.imports) for f in index.files)
        total_calls = sum(len(f.calls) for f in index.files)
        total_entrypoints = sum(len(f.entrypoints) for f in index.files)
        total_events = sum(len(f.events) for f in index.files)
        total_persistence = sum(len(f.persistence_models) for f in index.files)
        total_tests = sum(len(f.tests) for f in index.files)
        total_configs = sum(len(f.configurations) for f in index.files)
        total_type_rels = sum(len(f.type_relationships) for f in index.files)

        log(f"Files: {len(index.files)}")
        log(f"Symbols: {total_symbols}")
        log(f"Imports: {total_imports}")
        log(f"Calls: {total_calls}")
        log(f"Entrypoints: {total_entrypoints}")
        log(f"Events: {total_events}")
        log(f"Persistence Models: {total_persistence}")
        log(f"Tests: {total_tests}")
        log(f"Configurations: {total_configs}")
        log(f"Type Relationships: {total_type_rels}")
        log("=" * 80 + "\n")

        # Stage 1: Build symbol table
        log(f"[semantic] START Resolve Symbols")
        start = time.perf_counter()
        symbols: list[Symbol] = []
        symbol_index: dict[str, Symbol] = {}
        import_symbols: list[Symbol] = []

        for file_index in index.files:
            for sym in file_index.symbols:
                symbol = self._create_symbol(sym, file_index.path, language)
                symbols.append(symbol)
                symbol_index[symbol.id] = symbol

            for imp in file_index.imports:
                import_sym = self._create_import_symbol(imp, file_index.path, language)
                if import_sym:
                    symbols.append(import_sym)
                    symbol_index[import_sym.id] = import_sym
                    import_symbols.append(import_sym)

        elapsed = time.perf_counter() - start
        log(
            f"[semantic] END Resolve Symbols ({elapsed:.2f}s) - {len(symbols)} symbols, {len(import_symbols)} imports"
        )

        # Stage 2: Resolve imports → reference graph
        log(f"[semantic] START Resolve Imports")
        start = time.perf_counter()
        reference_edges: list[ReferenceEdge] = []
        self._watchdog_last_check = start

        # Build name index ONCE for O(1) lookups - CRITICAL for performance
        name_to_symbols: dict[str, list[Symbol]] = {}
        for sym_id, symbol in symbol_index.items():
            name_to_symbols.setdefault(symbol.name, []).append(symbol)

        # Progress reporting for large import sets
        total_imports_to_resolve = len(import_symbols)
        last_progress = -1

        for idx, imp_sym in enumerate(import_symbols):
            self._resolve_import_references_fast(
                imp_sym, name_to_symbols, reference_edges
            )

            # Watchdog check
            current = time.perf_counter()
            if current - self._watchdog_last_check >= self._watchdog_interval:
                pipeline_logger.log_pipeline(
                    f"  Still running: Resolve Imports - processed {idx} / {total_imports_to_resolve}, elapsed {current - start:.1f}s",
                    to_terminal=False,
                )
                self._watchdog_last_check = current

            # Report progress every 10% to pipeline.log
            if total_imports_to_resolve > 100:
                progress_pct = int((idx / total_imports_to_resolve) * 100)
                if progress_pct >= last_progress + 10:
                    pipeline_logger.log_pipeline(
                        f"  Resolving Imports: {idx} / {total_imports_to_resolve}",
                        to_terminal=False,
                    )
                    last_progress = progress_pct

        elapsed = time.perf_counter() - start
        log(
            f"[semantic] END Resolve Imports ({elapsed:.2f}s) - {len(reference_edges)} edges"
        )
        print(
            f"Resolving imports... ✓ {total_imports_to_resolve:,} imports ({elapsed * 1000:.0f}ms)"
        )

        # Stage 3: Build call graph from call entries
        print(f"[semantic] START Call Graph")
        start = time.perf_counter()
        call_edges: list[CallEdge] = []
        self._watchdog_last_check = start

        # Build callee name index ONCE for O(1) lookups - CRITICAL for performance
        callee_name_to_ids: dict[str, list[str]] = {}
        for sym_id, symbol in symbol_index.items():
            callee_name_to_ids.setdefault(symbol.name, []).append(sym_id)

        # Build local/imported/method resolution lookup indexes once
        resolved_imports: dict[tuple[str, str], str] = {}
        for edge in reference_edges:
            if "::import::" in edge.source_id:
                parts = edge.source_id.split("::import::")
                if len(parts) == 2:
                    file_uri, name = parts
                    file_path = file_uri.split("://")[-1]
                    resolved_imports[(file_path, name)] = edge.target_id

        file_symbol_map: dict[tuple[str, str], Symbol] = {}
        class_method_map: dict[tuple[str, str, str], Symbol] = {}
        for symbol in symbols:
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

        class_bases_map: dict[str, list[str]] = {}
        for file_index in index.files:
            for rel in file_index.type_relationships:
                if rel.relation_type == "extends":
                    source_id = f"{language}://{file_index.path}#{rel.source}"
                    class_bases_map.setdefault(source_id, []).append(rel.target)

        def resolve_base_class_id(file_path: str, base_name: str) -> str | None:
            local_id = f"{language}://{file_path}#{base_name}"
            if local_id in symbol_index:
                return local_id
            imported_id = resolved_imports.get((file_path, base_name))
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

        # Progress reporting for large call sets
        total_calls_to_resolve = sum(len(f.calls) for f in index.files)
        last_progress = -1

        for file_index in index.files:
            for call in file_index.calls:
                caller_id = _build_symbol_id(
                    language,
                    file_index.path,
                    call.caller,
                    kind="method" if call.caller_parent else "function",
                    parent=call.caller_parent,
                )

                callee_id = self._resolve_callee_id(
                    call.callee,
                    call.receiver,
                    caller_id,
                    file_index.path,
                    language,
                    symbol_index,
                    class_method_map,
                    file_symbol_map,
                    resolved_imports,
                    resolved_inheritance_map,
                    callee_name_to_ids,
                )

                # Record to call_resolution.json (up to 10k items to avoid memory bloat)
                if len(pipeline_logger.call_resolutions) < 10000:
                    pipeline_logger.record_call_resolution(
                        {
                            "caller_id": caller_id,
                            "callee_name": call.callee,
                            "receiver": call.receiver,
                            "resolved_callee_id": callee_id,
                            "success": callee_id is not None,
                        }
                    )

                if callee_id:
                    call_edges.append(
                        CallEdge(
                            caller_id=caller_id,
                            callee_id=callee_id,
                            call_type=call.call_type,
                            file=file_index.path,
                            line=call.line,
                            evidence=Evidence(
                                file_location=FileLocation(
                                    file=file_index.path,
                                    start_line=max(call.line, 1),
                                    end_line=max(call.line, 1),
                                ),
                            ),
                        )
                    )

            # Watchdog check
            current = time.perf_counter()
            if current - self._watchdog_last_check >= self._watchdog_interval:
                pipeline_logger.log_pipeline(
                    f"  Still running: Call Graph - processed {len(call_edges)} / {total_calls_to_resolve}, elapsed {current - start:.1f}s",
                    to_terminal=False,
                )
                self._watchdog_last_check = current

            # Report progress every 10% to pipeline.log
            if total_calls_to_resolve > 100:
                current_count = len(call_edges)
                progress_pct = int((current_count / total_calls_to_resolve) * 100)
                if progress_pct >= last_progress + 10:
                    pipeline_logger.log_pipeline(
                        f"  Resolving Calls: {current_count} / {total_calls_to_resolve}",
                        to_terminal=False,
                    )
                    last_progress = progress_pct

        elapsed = time.perf_counter() - start
        log = pipeline_logger.log_semantic
        log(f"[semantic] END Call Graph ({elapsed:.2f}s) - {len(call_edges)} edges")
        print(
            f"Resolving calls... ✓ {total_calls_to_resolve:,} calls ({elapsed * 1000:.0f}ms)"
        )

        # Log detailed analysis
        log(f"\n  [analysis] CALL GRAPH BREAKDOWN:")
        log(f"    Total calls resolved: {len(call_edges)}")
        log(f"    Total time: {elapsed:.2f}s")

        # Stage 4: Build type relationships
        log(f"[semantic] START Resolve Type Relationships")
        start = time.perf_counter()
        type_edges: list[TypeRelationshipEdge] = []
        for file_index in index.files:
            for rel in file_index.type_relationships:
                type_edge = self._create_type_edge(rel, file_index.path)
                if type_edge:
                    type_edges.append(type_edge)

        elapsed = time.perf_counter() - start
        log(
            f"[semantic] END Resolve Type Relationships ({elapsed:.2f}s) - {len(type_edges)} edges"
        )

        # Stage 5: Build entry points
        log(f"[semantic] START Resolve Entry Points")
        start = time.perf_counter()
        entry_points: list[EntryPoint] = []
        for file_index in index.files:
            for ep in file_index.entrypoints:
                entry_point = self._create_entry_point(ep, file_index.path, language)
                if entry_point:
                    entry_points.append(entry_point)

        elapsed = time.perf_counter() - start
        log(
            f"[semantic] END Resolve Entry Points ({elapsed:.2f}s) - {len(entry_points)} entry points"
        )

        # Stage 6: Build persistence models
        log(f"[semantic] START Resolve Persistence Models")
        start = time.perf_counter()
        persistence_models: list[PersistenceModel] = []
        for file_index in index.files:
            for pm in file_index.persistence_models:
                model = self._create_persistence_model(pm, file_index.path, language)
                if model:
                    persistence_models.append(model)

        elapsed = time.perf_counter() - start
        log(
            f"[semantic] END Resolve Persistence Models ({elapsed:.2f}s) - {len(persistence_models)} models"
        )

        # Stage 7: Build repository methods
        log(f"[semantic] START Resolve Repository Methods")
        start = time.perf_counter()
        repository_methods: list[RepositoryMethod] = []
        for file_index in index.files:
            for rm in file_index.repository_methods:
                method = self._create_repository_method(rm, file_index.path, language)
                if method:
                    repository_methods.append(method)

        elapsed = time.perf_counter() - start
        log(
            f"[semantic] END Resolve Repository Methods ({elapsed:.2f}s) - {len(repository_methods)} methods"
        )

        # Stage 8: Build event constructs
        log(f"[semantic] START Resolve Events")
        start = time.perf_counter()
        event_constructs: list[EventConstruct] = []
        for file_index in index.files:
            for ev in file_index.events:
                event = self._create_event(ev, file_index.path, language)
                if event:
                    event_constructs.append(event)

        elapsed = time.perf_counter() - start
        log(
            f"[semantic] END Resolve Events ({elapsed:.2f}s) - {len(event_constructs)} events"
        )

        # Stage 9: Build test definitions
        log(f"[semantic] START Resolve Tests")
        start = time.perf_counter()
        test_definitions: list[TestDefinition] = []
        for file_index in index.files:
            for td in file_index.tests:
                test = self._create_test(td, file_index.path, language)
                if test:
                    test_definitions.append(test)

        elapsed = time.perf_counter() - start
        log(
            f"[semantic] END Resolve Tests ({elapsed:.2f}s) - {len(test_definitions)} tests"
        )

        # Stage 10: Build configuration references
        log(f"[semantic] START Resolve Configurations")
        start = time.perf_counter()
        config_references: list[ConfigurationReference] = []
        for file_index in index.files:
            for cr in file_index.configurations:
                config = self._create_config(cr, file_index.path, language)
                if config:
                    config_references.append(config)

        elapsed = time.perf_counter() - start
        log(
            f"[semantic] END Resolve Configurations ({elapsed:.2f}s) - {len(config_references)} configs"
        )

        # Build graphs and print statistics
        log(f"\n[semantic] START Build Graphs")
        start = time.perf_counter()

        call_graph = CallGraph(edges=tuple(call_edges))
        reference_graph = ReferenceGraph(edges=tuple(reference_edges))
        type_relationship_graph = TypeRelationshipGraph(edges=tuple(type_edges))

        elapsed = time.perf_counter() - start
        log(f"[semantic] END Build Graphs ({elapsed:.2f}s)")

        # Log graph statistics
        log("\n" + "=" * 80)
        log("GRAPH STATISTICS")
        log("=" * 80)

        # Call graph stats
        call_nodes = len(
            set(e.caller_id for e in call_edges) | set(e.callee_id for e in call_edges)
        )
        log(f"\nCall Graph:")
        log(f"  Nodes: {call_nodes}")
        log(f"  Edges: {len(call_edges)}")
        if call_nodes > 0:
            avg_degree = (len(call_edges) * 2) / call_nodes
            log(f"  Average Degree: {avg_degree:.2f}")
            max_degree = self._calculate_max_degree(call_edges)
            log(f"  Maximum Degree: {max_degree}")

        # Reference graph stats
        ref_nodes = len(
            set(e.source_id for e in reference_edges)
            | set(e.target_id for e in reference_edges)
        )
        log(f"\nReference Graph:")
        log(f"  Nodes: {ref_nodes}")
        log(f"  Edges: {len(reference_edges)}")
        if ref_nodes > 0:
            avg_degree = (len(reference_edges) * 2) / ref_nodes
            log(f"  Average Degree: {avg_degree:.2f}")
            max_degree = self._calculate_max_degree(reference_edges)
            log(f"  Maximum Degree: {max_degree}")

        # Type relationship graph stats
        type_nodes = len(
            set(e.source_id for e in type_edges) | set(e.target_id for e in type_edges)
        )
        log(f"\nType Relationship Graph:")
        log(f"  Nodes: {type_nodes}")
        log(f"  Edges: {len(type_edges)}")
        if type_nodes > 0:
            avg_degree = (len(type_edges) * 2) / type_nodes
            log(f"  Average Degree: {avg_degree:.2f}")
            max_degree = self._calculate_max_degree(type_edges)
            log(f"  Maximum Degree: {max_degree}")

        log("=" * 80 + "\n")

        # Log statistics
        log(
            f"[semantic] RepositoryModel: {len(symbols)} symbols, {len(call_edges)} call edges, {len(reference_edges)} reference edges"
        )
        log(
            f"[semantic] Entry Points: {len(entry_points)}, Persistence Models: {len(persistence_models)}"
        )
        log(
            f"[semantic] Events: {len(event_constructs)}, Tests: {len(test_definitions)}, Configs: {len(config_references)}"
        )

        # Print top operations summary
        self._print_top_operations()

        return RepositoryModel(
            symbols=frozenset(symbols),
            call_graph=call_graph,
            reference_graph=reference_graph,
            type_relationship_graph=type_relationship_graph,
            entry_points=tuple(entry_points),
            persistence_models=tuple(persistence_models),
            repository_methods=tuple(repository_methods),
            event_constructs=tuple(event_constructs),
            test_definitions=tuple(test_definitions),
            configuration_references=tuple(config_references),
            metadata={"language": language},
        )

    def _calculate_max_degree(self, edges: list[Any]) -> int:
        """Calculate maximum degree in a graph from edges."""
        degree_map: dict[str, int] = {}
        for edge in edges:
            # For undirected degree calculation
            source = getattr(edge, "source_id", getattr(edge, "caller_id", ""))
            target = getattr(edge, "target_id", getattr(edge, "callee_id", ""))
            degree_map[source] = degree_map.get(source, 0) + 1
            degree_map[target] = degree_map.get(target, 0) + 1

        return max(degree_map.values()) if degree_map else 0

    def _print_top_operations(self):
        """Print top 25 slowest semantic operations."""
        log = pipeline_logger.log_semantic
        log("\n" + "=" * 80)
        log("TOP 25 SLOWEST SEMANTIC OPERATIONS")
        log("=" * 80)

        # Collect all operations with timing
        operations = []

        # We'll track key operations manually since we're not using decorators
        # This is a simplified version - in production you'd use the instrumentation framework

        log(
            "\nNote: Detailed per-operation timing requires decorator-based instrumentation."
        )
        log("Phase-level timing is shown above in START/END messages.")
        log("=" * 80 + "\n")

    def _create_symbol(
        self,
        entry: SymbolEntry,
        file_path: str,
        language: str,
    ) -> Symbol:
        """Create a Symbol from a SymbolEntry."""
        symbol_id = _build_symbol_id(
            language, file_path, entry.name, entry.kind, entry.parent
        )
        return Symbol(
            id=symbol_id,
            name=entry.name,
            kind=_to_symbol_kind(entry.kind),
            language=language,
            file=file_path,
            range=(entry.start_line, entry.end_line),
            visibility=_to_visibility(entry.visibility),
            evidence=Evidence(
                file_location=FileLocation(
                    file=file_path,
                    start_line=entry.start_line + 1,
                    end_line=entry.end_line + 1,
                ),
            ),
            properties=dict(entry.properties),
        )

    def _create_import_symbol(
        self,
        entry: ImportEntry,
        file_path: str,
        language: str,
    ) -> Symbol | None:
        """Create a Symbol for an import statement."""
        if not entry.names:
            return None
        first_name = entry.names[0]
        symbol_id = f"{language}://{file_path}::import::{first_name}"
        return Symbol(
            id=symbol_id,
            name=first_name,
            kind=SymbolKind.IMPORT,
            language=language,
            file=file_path,
            range=(entry.line, entry.line),
            visibility=SymbolVisibility.PUBLIC,
            evidence=Evidence(
                file_location=FileLocation(
                    file=file_path,
                    start_line=entry.line + 1,
                    end_line=entry.line + 1,
                ),
                import_references=(
                    ImportReference(
                        module=entry.module,
                        names=tuple(entry.names),
                        location=FileLocation(
                            file=file_path,
                            start_line=entry.line + 1,
                            end_line=entry.line + 1,
                        ),
                        import_type=entry.import_type,
                    ),
                ),
            ),
            properties={
                "type": entry.import_type,
                "module": entry.module,
                "names": list(entry.names),
            },
        )

    def _resolve_import_references_fast(
        self,
        import_symbol: Symbol,
        name_to_symbols: dict[str, list[Symbol]],
        reference_edges: list[ReferenceEdge],
    ) -> None:
        """Resolve references for an import symbol using pre-built name index."""
        start = time.perf_counter()
        imported_module = import_symbol.properties.get("module", "")
        imported_names = import_symbol.properties.get("names", [])

        for imported_name in imported_names:
            # O(1) lookup instead of O(n) scan
            candidates = name_to_symbols.get(imported_name, [])
            for symbol in candidates:
                # Skip self-references
                if symbol.id == import_symbol.id:
                    continue
                if imported_module in symbol.file:
                    edge = ReferenceEdge(
                        source_id=import_symbol.id,
                        target_id=symbol.id,
                        relation_type="import",
                        evidence=Evidence(
                            file_location=import_symbol.evidence.file_location
                            if import_symbol.evidence
                            else FileLocation(
                                file=import_symbol.file, start_line=1, end_line=1
                            ),
                        ),
                    )
                    reference_edges.append(edge)

        elapsed = time.perf_counter() - start
        if elapsed > 0.01:  # Only log if >10ms
            print(
                f"    [hotspot] resolve_import_references: {elapsed * 1000:.2f}ms for {len(imported_names)} names"
            )

    def _resolve_callee_id(
        self,
        callee_name: str,
        receiver: str,
        caller_id: str,
        file_path: str,
        language: str,
        symbol_index: dict[str, Symbol],
        class_method_map: dict[tuple[str, str, str], Symbol],
        file_symbol_map: dict[tuple[str, str], Symbol],
        resolved_imports: dict[tuple[str, str], str],
        resolved_inheritance_map: dict[str, list[str]],
        callee_name_to_ids: dict[str, list[str]],
    ) -> str | None:
        """Resolve a callee name to its symbol ID using pre-built lookup indexes."""
        # Case 1: Method call on self or cls
        if receiver in ("self", "cls"):
            if "#" in caller_id:
                parts = caller_id.split("#")[-1].split(".")
                if len(parts) == 2:
                    class_name = parts[0]
                    class_id = f"{language}://{file_path}#{class_name}"

                    method_sym = class_method_map.get(
                        (file_path, class_name, callee_name)
                    )
                    if method_sym:
                        return method_sym.id

                    queue = deque(resolved_inheritance_map.get(class_id, []))
                    visited = {class_id}
                    while queue:
                        base_id = queue.popleft()
                        if base_id in visited:
                            continue
                        visited.add(base_id)

                        if "#" in base_id:
                            base_uri, base_class = base_id.split("#")
                            base_file = base_uri.split("://")[-1]
                            method_sym = class_method_map.get(
                                (base_file, base_class, callee_name)
                            )
                            if method_sym:
                                return method_sym.id
                            queue.extend(resolved_inheritance_map.get(base_id, []))

        # Case 2: Receiver specified (e.g. object or module name)
        if receiver:
            imported_target = resolved_imports.get((file_path, receiver))
            if imported_target:
                if "#" in imported_target:
                    base_uri, class_name = imported_target.split("#")
                    target_file = base_uri.split("://")[-1]
                    method_sym = class_method_map.get(
                        (target_file, class_name, callee_name)
                    )
                    if method_sym:
                        return method_sym.id
                    queue = deque(resolved_inheritance_map.get(imported_target, []))
                    visited = {imported_target}
                    while queue:
                        base_id = queue.popleft()
                        if base_id in visited:
                            continue
                        visited.add(base_id)
                        if "#" in base_id:
                            base_uri, base_class = base_id.split("#")
                            base_file = base_uri.split("://")[-1]
                            method_sym = class_method_map.get(
                                (base_file, base_class, callee_name)
                            )
                            if method_sym:
                                return method_sym.id
                            queue.extend(resolved_inheritance_map.get(base_id, []))
                else:
                    target_file = imported_target.split("://")[-1].split("::")[0]
                    potential_id = f"{language}://{target_file}::{callee_name}"
                    if potential_id in symbol_index:
                        return potential_id

            local_class = file_symbol_map.get((file_path, receiver))
            if local_class and local_class.kind == SymbolKind.CLASS:
                method_sym = class_method_map.get((file_path, receiver, callee_name))
                if method_sym:
                    return method_sym.id

        # Case 3: No receiver (simple call)
        local_sym = file_symbol_map.get((file_path, callee_name))
        if local_sym:
            return local_sym.id

        imported_target = resolved_imports.get((file_path, callee_name))
        if imported_target:
            return imported_target

        candidates = callee_name_to_ids.get(callee_name, [])
        if candidates:
            return candidates[0]

        return None

    def _create_type_edge(
        self,
        rel: Any,
        file_path: str,
    ) -> TypeRelationshipEdge | None:
        """Create a TypeRelationshipEdge from a type relationship entry."""
        if not rel.source or not rel.target:
            return None
        return TypeRelationshipEdge(
            source_id=rel.source,
            target_id=rel.target,
            relation_type=rel.relation_type,
            metadata=dict(rel.metadata),
            evidence=Evidence(
                file_location=FileLocation(
                    file=file_path,
                    start_line=max(rel.line, 1),
                    end_line=max(rel.line, 1),
                ),
            ),
        )

    def _create_entry_point(
        self,
        ep: Any,
        file_path: str,
        language: str,
    ) -> EntryPoint | None:
        """Create an EntryPoint from an entrypoint entry."""
        if not ep.route or not ep.handler:
            return None

        handler_id = _build_symbol_id(language, file_path, ep.handler, "function")

        try:
            kind = EntryPointKind(ep.kind)
        except ValueError:
            kind = EntryPointKind.REST_ENDPOINT

        return EntryPoint(
            kind=kind,
            route=ep.route,
            handler_id=handler_id,
            evidence=Evidence(
                file_location=FileLocation(
                    file=file_path,
                    start_line=max(ep.line, 1),
                    end_line=max(ep.line, 1),
                ),
            ),
            metadata=dict(ep.metadata),
        )

    def _create_persistence_model(
        self,
        pm: Any,
        file_path: str,
        language: str,
    ) -> PersistenceModel | None:
        """Create a PersistenceModel from a persistence entry."""
        if not pm.name or not file_path:
            return None

        symbol_id = _build_symbol_id(language, file_path, pm.name, "class")

        return PersistenceModel(
            symbol_id=symbol_id,
            name=pm.name,
            kind=pm.kind,
            table_name=pm.table_name,
            framework=pm.framework,
            fields=tuple(pm.fields),
            relationships=tuple(pm.relationships),
            evidence=Evidence(
                file_location=FileLocation(
                    file=file_path,
                    start_line=max(pm.line, 1),
                    end_line=max(pm.line, 1),
                ),
            ),
            metadata=dict(pm.metadata),
        )

    def _create_repository_method(
        self,
        rm: Any,
        file_path: str,
        language: str,
    ) -> RepositoryMethod | None:
        """Create a RepositoryMethod from a repository method entry."""
        if not rm.symbol_name or not file_path:
            return None

        symbol_id = _build_symbol_id(language, file_path, rm.symbol_name, "function")

        return RepositoryMethod(
            symbol_id=symbol_id,
            name=rm.symbol_name,
            kind=rm.kind,
            model_symbol_id=rm.model_name,
            framework=rm.framework,
            query=rm.query,
            evidence=Evidence(
                file_location=FileLocation(
                    file=file_path,
                    start_line=max(rm.line, 1),
                    end_line=max(rm.line, 1),
                ),
            ),
            metadata=dict(rm.metadata),
        )

    def _create_event(
        self,
        ev: Any,
        file_path: str,
        language: str,
    ) -> EventConstruct | None:
        """Create an EventConstruct from an event entry."""
        if not ev.symbol_name or not file_path:
            return None

        symbol_id = _build_symbol_id(language, file_path, ev.symbol_name, "function")

        return EventConstruct(
            symbol_id=symbol_id,
            operation_kind=ev.operation_kind,
            event_name=ev.event_name,
            framework=ev.framework,
            file=file_path,
            line=ev.line,
            evidence=Evidence(
                file_location=FileLocation(
                    file=file_path,
                    start_line=max(ev.line, 1),
                    end_line=max(ev.line, 1),
                ),
            ),
            metadata=dict(ev.metadata),
        )

    def _create_test(
        self,
        td: Any,
        file_path: str,
        language: str,
    ) -> TestDefinition | None:
        """Create a TestDefinition from a test entry."""
        if not td.name or not file_path:
            return None

        symbol_id = _build_symbol_id(language, file_path, td.name, td.kind)

        fixtures = tuple(
            TestFixture(**f) if isinstance(f, dict) else f for f in td.fixtures
        )

        test_def = TestDefinition(
            symbol_id=symbol_id,
            name=td.name,
            kind=td.kind,
            framework=td.framework,
            file=file_path,
            line=td.line,
            fixtures=fixtures,
            assertions=tuple(td.assertions),
            evidence=Evidence(
                file_location=FileLocation(
                    file=file_path,
                    start_line=max(td.line, 1),
                    end_line=max(td.line, 1),
                ),
            ),
            metadata=dict(td.metadata),
        )

        return test_def

    def _create_config(
        self,
        cr: Any,
        file_path: str,
        language: str,
    ) -> ConfigurationReference | None:
        """Create a ConfigurationReference from a config entry."""
        if not cr.symbol_name or not cr.config_key or not file_path:
            return None

        symbol_id = _build_symbol_id(language, file_path, cr.symbol_name, "function")

        return ConfigurationReference(
            symbol_id=symbol_id,
            config_key=cr.config_key,
            kind=cr.kind,
            framework=cr.framework,
            file=file_path,
            line=cr.line,
            default_value=cr.default_value,
            evidence=Evidence(
                file_location=FileLocation(
                    file=file_path,
                    start_line=max(cr.line, 1),
                    end_line=max(cr.line, 1),
                ),
            ),
            metadata=dict(cr.metadata),
        )

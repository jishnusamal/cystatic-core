"""Shared model compiler - compiles a language-agnostic semantic graph into a RepositoryModel."""

from typing import Any

from engine.repository.model import (
    AsyncEntryPoint,
    CallEdge,
    CallGraph,
    CallReference,
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


class _ModelCompiler:
    """
    Language-agnostic compiler that transforms a semantic graph into a RepositoryModel.

    The semantic graph is a dict[file_path, file_data] where each file_data contains
    the extracted semantic elements produced by language-specific extractors.

    This is the core compilation pipeline that runs multiple passes over the extracted
    data to build a complete, language-independent RepositoryModel.

    This compiler is internal to the language adapter and should not be exposed
    as part of the public compiler API.
    """

    def compile(
        self, semantic_graph: dict[str, dict[str, Any]], language: str
    ) -> RepositoryModel:
        """
        Compile a semantic graph into a RepositoryModel.

        Args:
            semantic_graph: Dict mapping file paths to extracted file data
            language: Programming language identifier

        Returns:
            RepositoryModel containing the complete repository representation
        """
        symbols: list[Symbol] = []
        symbol_index: dict[str, Symbol] = {}
        call_graph_edges: list[CallEdge] = []
        reference_graph_edges: list[ReferenceEdge] = []
        type_relationship_edges: list[TypeRelationshipEdge] = []
        entry_points: list[EntryPoint] = []
        async_entry_points: list[AsyncEntryPoint] = []
        persistence_models: list[PersistenceModel] = []
        repository_methods: list[RepositoryMethod] = []
        event_constructs: list[EventConstruct] = []
        test_definitions: list[TestDefinition] = []
        configuration_references: list[ConfigurationReference] = []

        # Pass 1: Symbol Collection
        for file_path, file_data in semantic_graph.items():
            self._collect_symbols(file_path, language, file_data, symbols, symbol_index)

        # Build name index ONCE for O(1) lookups - CRITICAL for performance
        name_to_symbols: dict[str, list[Symbol]] = {}
        for sym_id, symbol in symbol_index.items():
            name_to_symbols.setdefault(symbol.name, []).append(symbol)

        # Pass 2: Reference Resolution (imports)
        for symbol in symbols:
            if symbol.kind == SymbolKind.IMPORT:
                self._resolve_import_references(
                    symbol, name_to_symbols, reference_graph_edges
                )

        # Pass 3: Call Graph
        for file_path, file_data in semantic_graph.items():
            for call in file_data.get("function_calls", []):
                self._process_call(
                    call, name_to_symbols, symbol_index, call_graph_edges
                )

        # Pass 4: Endpoint Discovery
        for file_path, file_data in semantic_graph.items():
            for endpoint in file_data.get("rest_endpoints", []):
                self._process_rest_endpoint(
                    endpoint, file_path, language, symbol_index, entry_points
                )

        # Pass 5: Type Relationships
        for file_path, file_data in semantic_graph.items():
            for rel in file_data.get("type_relationships", []):
                self._process_type_relationship(rel, type_relationship_edges)

        # Pass 6: Async Entry Points
        for file_path, file_data in semantic_graph.items():
            for aep in file_data.get("async_entry_points", []):
                self._process_async_entry_point(
                    aep, file_path, language, symbol_index, async_entry_points
                )

        # Pass 7: Persistence Models
        for file_path, file_data in semantic_graph.items():
            for pm in file_data.get("persistence_models", []):
                self._process_persistence_model(pm, persistence_models)

        # Pass 8: Repository Methods
        for file_path, file_data in semantic_graph.items():
            for rm in file_data.get("repository_methods", []):
                self._process_repository_method(rm, repository_methods)

        # Pass 9: Event Constructs
        for file_path, file_data in semantic_graph.items():
            for ev in file_data.get("event_constructs", []):
                self._process_event_construct(ev, event_constructs)

        # Pass 10: Test Definitions
        for file_path, file_data in semantic_graph.items():
            for td in file_data.get("test_definitions", []):
                self._process_test_definition(td, test_definitions)

        # Pass 11: Configuration References
        for file_path, file_data in semantic_graph.items():
            for cr in file_data.get("configuration_references", []):
                self._process_configuration_reference(cr, configuration_references)

        return RepositoryModel(
            symbols=frozenset(symbols),
            call_graph=CallGraph(edges=tuple(call_graph_edges)),
            reference_graph=ReferenceGraph(edges=tuple(reference_graph_edges)),
            type_relationship_graph=TypeRelationshipGraph(
                edges=tuple(type_relationship_edges)
            ),
            entry_points=tuple(entry_points),
            async_entry_points=tuple(async_entry_points),
            persistence_models=tuple(persistence_models),
            repository_methods=tuple(repository_methods),
            event_constructs=tuple(event_constructs),
            test_definitions=tuple(test_definitions),
            configuration_references=tuple(configuration_references),
        )

    def _collect_symbols(
        self,
        file_path: str,
        language: str,
        file_data: dict[str, Any],
        symbols: list[Symbol],
        symbol_index: dict[str, Symbol],
    ) -> None:
        """Collect symbols from a file's extracted data."""
        # Collect functions
        for func in file_data.get("functions", []):
            symbol = self._create_function_symbol(file_path, language, func)
            symbols.append(symbol)
            symbol_index[symbol.id] = symbol

        # Collect classes with methods
        for cls in file_data.get("classes", []):
            class_symbol = self._create_class_symbol(file_path, language, cls)
            symbols.append(class_symbol)
            symbol_index[class_symbol.id] = class_symbol

            for method in cls.get("methods", []):
                method_symbol = self._create_method_symbol(
                    file_path, language, method, cls["name"]
                )
                symbols.append(method_symbol)
                symbol_index[method_symbol.id] = method_symbol

        # Collect imports
        for imp in file_data.get("imports", []):
            import_symbol = self._create_import_symbol(file_path, language, imp)
            if import_symbol:
                symbols.append(import_symbol)
                symbol_index[import_symbol.id] = import_symbol

    def _create_function_symbol(
        self, file_path: str, language: str, func_data: dict
    ) -> Symbol:
        """Create a Symbol for a function."""
        func_name = func_data["name"]
        symbol_id = f"{language}://{file_path}::{func_name}"
        start_line = func_data.get("start_line", 0)
        end_line = func_data.get("end_line", 0)

        return Symbol(
            id=symbol_id,
            name=func_name,
            kind=SymbolKind.FUNCTION,
            language=language,
            file=file_path,
            range=(start_line, end_line),
            visibility=SymbolVisibility(func_data.get("visibility", "public")),
            evidence=Evidence(
                file_location=FileLocation(
                    file=file_path,
                    start_line=start_line + 1,
                    end_line=end_line + 1,
                )
            ),
            properties=func_data.get("properties", {}),
        )

    def _create_class_symbol(
        self, file_path: str, language: str, class_data: dict
    ) -> Symbol:
        """Create a Symbol for a class."""
        class_name = class_data["name"]
        symbol_id = f"{language}://{file_path}#{class_name}"
        start_line = class_data.get("start_line", 0)
        end_line = class_data.get("end_line", 0)

        return Symbol(
            id=symbol_id,
            name=class_name,
            kind=SymbolKind.CLASS,
            language=language,
            file=file_path,
            range=(start_line, end_line),
            visibility=SymbolVisibility(class_data.get("visibility", "public")),
            evidence=Evidence(
                file_location=FileLocation(
                    file=file_path,
                    start_line=start_line + 1,
                    end_line=end_line + 1,
                )
            ),
            properties=class_data.get("properties", {}),
        )

    def _create_method_symbol(
        self, file_path: str, language: str, method_data: dict, class_name: str
    ) -> Symbol:
        """Create a Symbol for a method."""
        method_name = method_data["name"]
        symbol_id = f"{language}://{file_path}#{class_name}.{method_name}"
        start_line = method_data.get("start_line", 0)
        end_line = method_data.get("end_line", 0)

        return Symbol(
            id=symbol_id,
            name=method_name,
            kind=SymbolKind.METHOD,
            language=language,
            file=file_path,
            range=(start_line, end_line),
            visibility=SymbolVisibility(method_data.get("visibility", "public")),
            evidence=Evidence(
                file_location=FileLocation(
                    file=file_path,
                    start_line=start_line + 1,
                    end_line=end_line + 1,
                )
            ),
            properties=method_data.get("properties", {}),
        )

    def _create_import_symbol(
        self, file_path: str, language: str, import_data: dict
    ) -> Symbol | None:
        """Create a Symbol for an import statement."""
        imp_type = import_data.get("type", "import")
        module = import_data.get("module", "")
        names = import_data.get("names", [])

        if not names:
            return None

        first_name = names[0]
        symbol_id = f"{language}://{file_path}::import::{first_name}"

        return Symbol(
            id=symbol_id,
            name=first_name,
            kind=SymbolKind.IMPORT,
            language=language,
            file=file_path,
            range=(0, 0),
            visibility=SymbolVisibility.PUBLIC,
            evidence=Evidence(
                file_location=FileLocation(
                    file=file_path,
                    start_line=1,
                    end_line=1,
                ),
                import_references=(
                    ImportReference(
                        module=module,
                        names=tuple(names),
                        location=FileLocation(file=file_path, start_line=1, end_line=1),
                        import_type=imp_type,
                    ),
                ),
            ),
            properties={"type": imp_type, "module": module, "names": names},
        )

    def _resolve_import_references(
        self,
        import_symbol: Symbol,
        name_to_symbols: dict[str, list[Symbol]],
        reference_graph_edges: list[ReferenceEdge],
    ) -> None:
        """Resolve references for an import symbol using pre-built name index."""
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
                    reference_graph_edges.append(edge)

    def _matches_import(self, symbol: Symbol, module: str, name: str) -> bool:
        """Check if a symbol matches an import statement."""
        if symbol.name != name:
            return False

        symbol_file = symbol.file
        if module and module in symbol_file:
            return True

        return False

    def _process_call(
        self,
        call: dict[str, Any],
        name_to_symbols: dict[str, list[Symbol]],
        symbol_index: dict[str, Symbol],
        call_graph_edges: list[CallEdge],
    ) -> None:
        """Process a single function call and create a call edge."""
        caller_id = call.get("caller_id")
        callee_name = call.get("callee_name")
        call_type = call.get("call_type", "direct")
        call_file = call.get("file", "")
        call_line = call.get("line", 0)

        if not caller_id or not callee_name:
            return

        callee_id = self._resolve_callee_id(
            callee_name, caller_id, name_to_symbols, symbol_index
        )

        if callee_id:
            caller_symbol = symbol_index.get(caller_id)
            caller_file = caller_symbol.file if caller_symbol else call_file

            resolved_file = call_file or caller_file
            if not resolved_file:
                return

            edge = CallEdge(
                caller_id=caller_id,
                callee_id=callee_id,
                call_type=call_type,
                file=call_file,
                line=call_line,
                evidence=Evidence(
                    file_location=FileLocation(
                        file=resolved_file,
                        start_line=max(call_line, 1),
                        end_line=max(call_line, 1),
                    ),
                    call_references=(
                        CallReference(
                            caller_symbol_id=caller_id,
                            callee_name=callee_name,
                            location=FileLocation(
                                file=resolved_file,
                                start_line=max(call_line, 1),
                                end_line=max(call_line, 1),
                            ),
                            call_type=call_type,
                        ),
                    ),
                ),
            )
            call_graph_edges.append(edge)

    def _resolve_callee_id(
        self,
        callee_name: str,
        caller_id: str,
        name_to_symbols: dict[str, list[Symbol]],
        symbol_index: dict[str, Symbol],
    ) -> str | None:
        """Resolve a callee name to a symbol id using index."""
        # Try exact name match using index (O(1) instead of O(S))
        candidates = name_to_symbols.get(callee_name, [])
        if candidates:
            return candidates[0].id  # Return first match

        # Try to construct id from caller's file path
        if "::" in caller_id:
            parts = caller_id.split("::")
            if len(parts) == 2:
                potential_id = f"{parts[0]}::{callee_name}"
                if potential_id in symbol_index:
                    return potential_id

        return None

    def _process_rest_endpoint(
        self,
        endpoint: dict[str, Any],
        file_path: str,
        language: str,
        symbol_index: dict[str, Symbol],
        entry_points: list[EntryPoint],
    ) -> None:
        """Process a REST endpoint and create an EntryPoint."""
        method = endpoint.get("method", "GET")
        route = endpoint.get("route", "")
        handler_name = endpoint.get("handler", "")

        if not route or not handler_name:
            return

        handler_id = f"{language}://{file_path}::{handler_name}"

        if handler_id not in symbol_index:
            return

        entry_point = EntryPoint(
            kind=EntryPointKind.REST_ENDPOINT,
            route=f"{method} {route}",
            handler_id=handler_id,
            evidence=Evidence(
                file_location=FileLocation(
                    file=file_path,
                    start_line=1,
                    end_line=1,
                )
            ),
            metadata={
                "method": method,
                "route": route,
                "handler": handler_name,
                "file": file_path,
            },
        )

        entry_points.append(entry_point)

    def _process_type_relationship(
        self,
        rel: dict[str, Any],
        type_relationship_edges: list[TypeRelationshipEdge],
    ) -> None:
        """Process a type relationship and create a TypeRelationshipEdge."""
        source = rel.get("source_sym", "")
        target = rel.get("target_sym", "")
        relation_type = rel.get("relation_type", "extends")
        metadata = rel.get("metadata", {})

        if not source or not target:
            return

        file_path = metadata.get("file", "")
        if not file_path:
            return

        edge = TypeRelationshipEdge(
            source_id=source,
            target_id=target,
            relation_type=relation_type,
            metadata=metadata,
            evidence=Evidence(
                file_location=FileLocation(
                    file=file_path,
                    start_line=max(metadata.get("line", 1), 1),
                    end_line=max(metadata.get("line", 1), 1),
                ),
            ),
        )
        type_relationship_edges.append(edge)

    def _process_async_entry_point(
        self,
        aep: dict[str, Any],
        file_path: str,
        language: str,
        symbol_index: dict[str, Symbol],
        async_entry_points: list[AsyncEntryPoint],
    ) -> None:
        """Process an async entry point."""
        kind = aep.get("kind", "worker_entry")
        handler_name = aep.get("handler", "")
        trigger = aep.get("trigger", "")
        framework = aep.get("framework", "")

        if not handler_name:
            return

        handler_id = f"{language}://{file_path}::{handler_name}"
        metadata = aep.get("metadata", {})

        async_ep = AsyncEntryPoint(
            kind=kind,
            handler_id=handler_id,
            trigger=trigger,
            framework=framework,
            evidence=Evidence(
                file_location=FileLocation(
                    file=file_path,
                    start_line=1,
                    end_line=1,
                )
            ),
            metadata=metadata,
        )
        async_entry_points.append(async_ep)

    def _process_persistence_model(
        self,
        pm: dict[str, Any],
        persistence_models: list[PersistenceModel],
    ) -> None:
        """Process a persistence model construct."""
        symbol_id = pm.get("symbol_id", "")
        name = pm.get("name", "")
        kind = pm.get("kind", "table")
        table_name = pm.get("table_name", "")
        framework = pm.get("framework", "")
        fields = tuple(pm.get("fields", []))
        relationships = tuple(pm.get("relationships", []))
        file_path = pm.get("file", "")
        line = pm.get("line", 0)

        if not symbol_id or not name:
            return

        if not file_path:
            return

        model = PersistenceModel(
            symbol_id=symbol_id,
            name=name,
            kind=kind,
            table_name=table_name,
            framework=framework,
            fields=fields,
            relationships=relationships,
            evidence=Evidence(
                file_location=FileLocation(
                    file=file_path,
                    start_line=max(line, 1),
                    end_line=max(line, 1),
                )
            ),
            metadata=pm.get("metadata", {}),
        )
        persistence_models.append(model)

    def _process_repository_method(
        self,
        rm: dict[str, Any],
        repository_methods: list[RepositoryMethod],
    ) -> None:
        """Process a repository method."""
        symbol_id = rm.get("symbol_id", "")
        name = rm.get("name", "")
        kind = rm.get("kind", "custom")
        model_id = rm.get("model_symbol_id", "")
        framework = rm.get("framework", "")
        query = rm.get("query", "")
        file_path = rm.get("file", "")
        line = rm.get("line", 0)

        if not symbol_id or not name:
            return

        if not file_path:
            return

        method = RepositoryMethod(
            symbol_id=symbol_id,
            name=name,
            kind=kind,
            model_symbol_id=model_id,
            framework=framework,
            query=query,
            evidence=Evidence(
                file_location=FileLocation(
                    file=file_path,
                    start_line=max(line, 1),
                    end_line=max(line, 1),
                )
            ),
            metadata=rm.get("metadata", {}),
        )
        repository_methods.append(method)

    def _process_event_construct(
        self,
        ev: dict[str, Any],
        event_constructs: list[EventConstruct],
    ) -> None:
        """Process an event construct."""
        symbol_id = ev.get("symbol_id", "")
        operation_kind = ev.get("operation_kind", "publish")
        event_name = ev.get("event_name", "")
        framework = ev.get("framework", "")
        file_path = ev.get("file", "")
        line = ev.get("line", 0)

        if not symbol_id:
            return

        if not file_path:
            return

        ec = EventConstruct(
            symbol_id=symbol_id,
            operation_kind=operation_kind,
            event_name=event_name,
            framework=framework,
            file=file_path,
            line=line,
            evidence=Evidence(
                file_location=FileLocation(
                    file=file_path,
                    start_line=max(line, 1),
                    end_line=max(line, 1),
                )
            ),
            metadata=ev.get("metadata", {}),
        )
        event_constructs.append(ec)

    def _process_test_definition(
        self,
        td: dict[str, Any],
        test_definitions: list[TestDefinition],
    ) -> None:
        """Process a test definition."""
        symbol_id = td.get("symbol_id", "")
        name = td.get("name", "")
        kind = td.get("kind", "function")
        framework = td.get("framework", "other")
        file_path = td.get("file", "")
        line = td.get("line", 0)
        fixtures = tuple(
            TestFixture(**f) if isinstance(f, dict) else f
            for f in td.get("fixtures", [])
        )
        assertions = tuple(td.get("assertions", []))

        if not symbol_id or not name:
            return

        if not file_path:
            return

        test_def = TestDefinition(
            symbol_id=symbol_id,
            name=name,
            kind=kind,
            framework=framework,
            file=file_path,
            line=line,
            fixtures=fixtures,
            assertions=assertions,
            evidence=Evidence(
                file_location=FileLocation(
                    file=file_path,
                    start_line=max(line, 1),
                    end_line=max(line, 1),
                )
            ),
            metadata=td.get("metadata", {}),
        )
        test_definitions.append(test_def)

        # Also process nested test methods if this is a test class
        for method_data in td.get("test_methods", []):
            self._process_test_definition(method_data, test_definitions)

    def _process_configuration_reference(
        self,
        cr: dict[str, Any],
        configuration_references: list[ConfigurationReference],
    ) -> None:
        """Process a configuration reference."""
        symbol_id = cr.get("symbol_id", "")
        config_key = cr.get("config_key", "")
        kind = cr.get("kind", "environment_variable")
        framework = cr.get("framework", "")
        file_path = cr.get("file", "")
        line = cr.get("line", 0)
        default_value = cr.get("default_value", "")

        if not symbol_id:
            return

        if not config_key:
            return

        if not file_path:
            return

        config_ref = ConfigurationReference(
            symbol_id=symbol_id,
            config_key=config_key,
            kind=kind,
            framework=framework,
            file=file_path,
            line=line,
            default_value=default_value,
            evidence=Evidence(
                file_location=FileLocation(
                    file=file_path,
                    start_line=max(line, 1),
                    end_line=max(line, 1),
                )
            ),
            metadata=cr.get("metadata", {}),
        )
        configuration_references.append(config_ref)

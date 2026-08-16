import gc
from typing import Any
from zlib import adler32

from engine.repository.facts import (
    Call,
    DatabaseRelationship,
    Endpoint,
    EventPublication,
    EventSubscription,
    File,
    FileId,
    Import,
    ImportType,
    Reference,
    Symbol,
    SymbolId,
    TestRelationship,
    TypeRelationship,
)
from engine.repository.indexing.sink import RepositoryFactSink


def build_symbol_fqn(
    language: str, file_path: str, name: str, kind: str = "", parent: str = ""
) -> str:
    """Build a canonical symbol ID string (FQN) for a symbol entry."""
    if parent:
        return f"{language}://{file_path}#{parent}.{name}"
    if kind == "class":
        return f"{language}://{file_path}#{name}"
    if kind == "module":
        return f"{language}://{file_path}"
    return f"{language}://{file_path}::{name}"


class RepositoryIndexer:
    """
    Orchestrates streaming fact extraction from a repository snapshot.

    Processes one file at a time, parses it using language adapters,
    extracts flat facts, writes them to the RepositoryFactSink, and releases
    the AST and file-scoped context before moving to the next file.
    """

    def __init__(self, sink: RepositoryFactSink) -> None:
        self.sink = sink
        self._file_id_map: dict[str, FileId] = {}
        self._next_file_id = 1

        self._symbol_id_map: dict[str, SymbolId] = {}
        self._symbol_fqn_map: dict[SymbolId, str] = {}
        self._next_symbol_id = 1

    def get_or_create_file_id(self, path: str) -> FileId:
        """Get or allocate a stable FileId for a file path."""
        normalized_path = path.replace("\\", "/")
        if normalized_path not in self._file_id_map:
            file_id = FileId(self._next_file_id)
            self._next_file_id += 1
            self._file_id_map[normalized_path] = file_id
        return self._file_id_map[normalized_path]

    def get_or_create_symbol_id(self, fqn: str) -> SymbolId:
        """Get or allocate a stable SymbolId for a symbol FQN."""
        if fqn not in self._symbol_id_map:
            sym_id = SymbolId(self._next_symbol_id)
            self._next_symbol_id += 1
            self._symbol_id_map[fqn] = sym_id
            self._symbol_fqn_map[sym_id] = fqn
        return self._symbol_id_map[fqn]

    def get_symbol_fqn(self, symbol_id: SymbolId) -> str | None:
        """Retrieve the canonical FQN string for a SymbolId."""
        return self._symbol_fqn_map.get(symbol_id)

    def index_repository(self, repository_input: dict[str, Any], adapter: Any) -> None:
        """
        Streamingly index a repository snapshot using the dynamically detected adapter per file.

        Args:
            repository_input: Snapshots dictionary with 'files' mapping path to content.
            adapter: Fallback language adapter (e.g. PythonLanguageAdapter, JavaLanguageAdapter).
        """
        import os
        from engine.language.builtins import create_default_language_registry

        files = repository_input.get("files", {})
        language = repository_input.get("language", adapter.get_language())
        registry = create_default_language_registry()

        # Invariant check: ensure file-scoped extraction and release of AST
        for file_path, content in files.items():
            if content is None:
                continue

            self.sink.begin()
            try:
                file_id = self.get_or_create_file_id(file_path)

                # Determine the language and adapter for this file dynamically
                file_lang = None
                file_adapter = None

                filename = os.path.basename(file_path)
                plugin = registry.find_by_filename(filename)
                if not plugin:
                    _, ext = os.path.splitext(file_path)
                    plugin = registry.find_by_extension(ext)

                if plugin:
                    file_lang = plugin.spec.id
                    file_adapter = plugin.create_adapter()
                elif adapter:
                    file_lang = language
                    file_adapter = adapter
                else:
                    file_lang = "unknown"
                    file_adapter = None

                # Step 1: Write File Fact
                file_fact = File(id=file_id, path=file_path, language=file_lang)
                self.sink.add_file(file_fact)

                # Step 2: Parse and Index single file scoped to local scope
                if file_adapter:
                    file_index = file_adapter._index_single_file(file_path, content, file_lang)
                    # Step 3: Extract and emit facts to the sink
                    self._extract_file_facts(file_index, file_id, file_lang)

                # Step 4: Flush / commit the facts for this file
                self.sink.flush()
            except Exception as e:
                if hasattr(self.sink, "rollback"):
                    self.sink.rollback()
                raise e
            finally:
                # Step 5: Release file-scoped context and AST
                if "file_index" in locals():
                    del file_index
                gc.collect()


    def _extract_file_facts(
        self, file_index: Any, file_id: FileId, language: str
    ) -> None:
        """Extract flat facts from a file index and write them to the sink."""
        # 1. Symbols
        for sym in file_index.symbols:
            fqn = build_symbol_fqn(
                language, file_index.path, sym.name, sym.kind, sym.parent
            )
            sym_id = self.get_or_create_symbol_id(fqn)

            parent_id = None
            if sym.parent:
                parent_fqn = build_symbol_fqn(
                    language, file_index.path, sym.parent, "class", ""
                )
                parent_id = self.get_or_create_symbol_id(parent_fqn)

            from engine.repository.facts import SymbolKind, SymbolVisibility

            try:
                kind = SymbolKind(sym.kind)
            except ValueError:
                kind = SymbolKind.FUNCTION
            try:
                visibility = SymbolVisibility(sym.visibility)
            except ValueError:
                visibility = SymbolVisibility.PUBLIC

            symbol_fact = Symbol(
                id=sym_id,
                name=sym.name,
                file_id=file_id,
                kind=kind,
                language=language,
                start_line=sym.start_line,
                end_line=sym.end_line,
                visibility=visibility,
                parent_symbol_id=parent_id,
            )
            self.sink.add_symbol(symbol_fact)

        # 2. Imports
        for imp in file_index.imports:
            # target_file_id will be resolved in Phase B/semantic compiler, initially None
            # or we can compute a stable FileId if the target path is known or guessable
            try:
                imp_type = ImportType(imp.import_type)
            except ValueError:
                imp_type = ImportType.STANDARD

            import_fact = Import(
                source_file_id=file_id,
                target_file_id=None,
                module=imp.module,
                imported_name=", ".join(imp.names) if imp.names else "",
                import_type=imp_type,
            )
            self.sink.add_import(import_fact)

        # 3. Calls
        for call in file_index.calls:
            # Caller
            caller_parent = getattr(call, "caller_parent", "")
            caller_fqn = build_symbol_fqn(
                language, file_index.path, call.caller, parent=caller_parent
            )
            caller_id = self.get_or_create_symbol_id(caller_fqn)

            # Callee FQN: since unresolved, we assign a placeholder FQN for the callee
            callee_fqn = f"unresolved://{call.callee}"
            callee_id = self.get_or_create_symbol_id(callee_fqn)

            from engine.repository.facts import CallType

            try:
                c_type = CallType(call.call_type)
            except ValueError:
                c_type = CallType.DIRECT

            call_fact = Call(
                caller_id=caller_id,
                callee_id=callee_id,
                call_type=c_type,
            )
            self.sink.add_call(call_fact)

        # 4. References
        for ref in file_index.references:
            parent_sym = getattr(ref, "parent_symbol", "")
            source_fqn = (
                build_symbol_fqn(language, file_index.path, parent_sym)
                if parent_sym
                else f"{language}://{file_index.path}"
            )
            source_id = self.get_or_create_symbol_id(source_fqn)

            target_fqn = f"unresolved://{ref.name}"
            target_id = self.get_or_create_symbol_id(target_fqn)

            from engine.repository.facts import ReferenceType

            ref_fact = Reference(
                source_id=source_id,
                target_id=target_id,
                relation_type=ReferenceType.REFERENCE,
            )
            self.sink.add_reference(ref_fact)

        # 5. Type Relationships
        for tr in file_index.type_relationships:
            source_fqn = build_symbol_fqn(language, file_index.path, tr.source)
            source_id = self.get_or_create_symbol_id(source_fqn)

            target_fqn = f"unresolved://{tr.target}"
            target_id = self.get_or_create_symbol_id(target_fqn)

            from engine.repository.facts import TypeRelationshipType

            try:
                tr_type = TypeRelationshipType(tr.relation_type)
            except ValueError:
                tr_type = TypeRelationshipType.EXTENDS

            tr_fact = TypeRelationship(
                source_id=source_id,
                target_id=target_id,
                relationship_type=tr_type,
            )
            self.sink.add_type_relationship(tr_fact)

        # 6. Endpoints (Entrypoints)
        for ep in file_index.entrypoints:
            handler_fqn = build_symbol_fqn(language, file_index.path, ep.handler)
            handler_id = self.get_or_create_symbol_id(handler_fqn)

            from engine.repository.facts import EndpointId, EndpointMethod

            # Create a stable integer ID for the endpoint
            ep_id_int = adler32(f"{ep.route}:{ep.handler}".encode()) & 0xFFFFFFFF
            ep_id = EndpointId(ep_id_int)

            method_str = ep.route.split(" ")[0] if " " in ep.route else "GET"
            try:
                method = EndpointMethod(method_str)
            except ValueError:
                method = EndpointMethod.ANY

            ep_fact = Endpoint(
                id=ep_id,
                symbol_id=handler_id,
                method=method,
                path=ep.route.split(" ")[1] if " " in ep.route else ep.route,
                framework=ep.framework,
            )
            self.sink.add_endpoint(ep_fact)

        # 7. Persistence Models
        for pm in file_index.persistence_models:
            model_fqn = build_symbol_fqn(
                language, file_index.path, pm.name, kind="class"
            )
            model_id = self.get_or_create_symbol_id(model_fqn)

            from engine.repository.facts import DatabaseRelationshipType, ResourceId

            res_id = (
                ResourceId(adler32(pm.table_name.encode()) & 0xFFFFFFFF)
                if pm.table_name
                else ResourceId(0)
            )

            db_fact = DatabaseRelationship(
                symbol_id=model_id,
                resource_id=res_id,
                relationship_type=DatabaseRelationshipType.READ,  # Default
            )
            self.sink.add_database_relationship(db_fact)

        # 8. Events
        for ev in file_index.events:
            symbol_fqn = build_symbol_fqn(language, file_index.path, ev.symbol_name)
            symbol_id = self.get_or_create_symbol_id(symbol_fqn)

            from engine.repository.facts import (
                EventId,
                EventPublicationType,
                EventSubscriptionType,
            )

            event_id = EventId(adler32(ev.event_name.encode()) & 0xFFFFFFFF)

            if ev.operation_kind in ("publish", "emit", "send", "produce"):
                try:
                    pub_type = EventPublicationType(ev.operation_kind)
                except ValueError:
                    pub_type = EventPublicationType.PUBLISH
                self.sink.add_event_publication(
                    EventPublication(
                        symbol_id=symbol_id,
                        event_id=event_id,
                        publication_type=pub_type,
                    )
                )
            else:
                try:
                    sub_type = EventSubscriptionType(ev.operation_kind)
                except ValueError:
                    sub_type = EventSubscriptionType.SUBSCRIBE
                self.sink.add_event_subscription(
                    EventSubscription(
                        symbol_id=symbol_id,
                        event_id=event_id,
                        subscription_type=sub_type,
                    )
                )

        # 9. Tests
        for test in file_index.tests:
            test_fqn = build_symbol_fqn(language, file_index.path, test.name)
            test_id = self.get_or_create_symbol_id(test_fqn)

            # Check if covers/references any symbols
            # TestEntry metadata can hold targets
            targets = test.metadata.get("covers", [])
            for target_name in targets:
                target_fqn = build_symbol_fqn(language, file_index.path, target_name)
                target_id = self.get_or_create_symbol_id(target_fqn)

                from engine.repository.facts import TestRelationshipType

                self.sink.add_test_relationship(
                    TestRelationship(
                        test_symbol_id=test_id,
                        target_symbol_id=target_id,
                        relationship_type=TestRelationshipType.COVERS,
                    )
                )

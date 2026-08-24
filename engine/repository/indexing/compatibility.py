from engine.repository.facts import RepositoryFacts
from engine.repository.indexing.indexer import RepositoryIndexer
from engine.repository.model.repository_index import (
    CallEntry,
    EntrypointEntry,
    EventEntry,
    FileIndex,
    ImportEntry,
    PersistenceEntry,
    RawReference,
    RepositoryIndex,
    RepositoryMethodEntry,
    SymbolEntry,
    TestEntry,
    TypeRelationshipEntry,
)


def _extract_name_from_fqn(fqn: str) -> str:
    """Helper to extract symbol name from FQN."""
    if fqn.startswith("unresolved://"):
        return fqn[len("unresolved://") :]

    # E.g. python://file.py#Class.method or python://file.py::func
    if "#" in fqn:
        parts = fqn.split("#")[-1]
        return parts.split(".")[-1]
    if "::" in fqn:
        return fqn.split("::")[-1]

    # Fallback to last path segment or full FQN
    return fqn.split("/")[-1]


def _extract_parent_from_fqn(fqn: str) -> str:
    """Helper to extract parent class name from FQN if exists."""
    if "#" in fqn:
        parts = fqn.split("#")[-1]
        if "." in parts:
            return parts.split(".")[0]
        # It's a class itself, so no parent class
    return ""


class FactsToIndexAdapter:
    """
    [TEMPORARY - MARKED FOR REMOVAL IN NEXT PHASES]

    Compatibility layer that converts the new flat RepositoryFacts back to
    the old memory-heavy RepositoryIndex so existing downstream compilers/consumers
    work unchanged.
    """

    def __init__(self, indexer: RepositoryIndexer) -> None:
        self.indexer = indexer

    def convert(self, facts: RepositoryFacts, language: str) -> RepositoryIndex:
        """Convert RepositoryFacts to RepositoryIndex."""
        file_indices: list[FileIndex] = []

        for file_fact in facts.files:
            file_path = file_fact.path
            file_id = file_fact.id

            # Lists for this file's entries
            symbols_entries: list[SymbolEntry] = []
            imports_entries: list[ImportEntry] = []
            references_entries: list[RawReference] = []
            calls_entries: list[CallEntry] = []
            entrypoints_entries: list[EntrypointEntry] = []
            type_relationships_entries: list[TypeRelationshipEntry] = []
            persistence_entries: list[PersistenceEntry] = []
            repository_methods_entries: list[RepositoryMethodEntry] = []
            event_entries: list[EventEntry] = []
            test_entries: list[TestEntry] = []

            # 1. Symbols
            for sym in facts.symbols:
                if sym.file_id == file_id:
                    parent_name = ""
                    if sym.parent_symbol_id is not None:
                        parent_fqn = self.indexer.get_symbol_fqn(sym.parent_symbol_id)
                        if parent_fqn:
                            parent_name = _extract_name_from_fqn(parent_fqn)

                    symbols_entries.append(
                        SymbolEntry(
                            name=sym.name,
                            kind=sym.kind.value,
                            file=file_path,
                            start_line=sym.start_line,
                            end_line=sym.end_line,
                            visibility=sym.visibility.value,
                            parent=parent_name,
                        )
                    )

            # 2. Imports
            for imp in facts.imports:
                if imp.source_file_id == file_id:
                    names_tuple = (
                        tuple(imp.imported_name.split(", "))
                        if imp.imported_name
                        else ()
                    )
                    imports_entries.append(
                        ImportEntry(
                            module=imp.module,
                            names=names_tuple,
                            import_type=imp.import_type,
                            file=file_path,
                        )
                    )

            # 3. Calls
            for call in facts.calls:
                caller_fqn = self.indexer.get_symbol_fqn(call.caller_id)
                if caller_fqn and file_path in caller_fqn:
                    caller_name = _extract_name_from_fqn(caller_fqn)
                    caller_parent = _extract_parent_from_fqn(caller_fqn)

                    callee_fqn = self.indexer.get_symbol_fqn(call.callee_id)
                    callee_name = (
                        _extract_name_from_fqn(callee_fqn) if callee_fqn else "unknown"
                    )

                    calls_entries.append(
                        CallEntry(
                            caller=caller_name,
                            callee=callee_name,
                            call_type=call.call_type.value,
                            file=file_path,
                            caller_parent=caller_parent,
                        )
                    )

            # 4. References
            for ref in facts.references:
                source_fqn = self.indexer.get_symbol_fqn(ref.source_id)
                if source_fqn and file_path in source_fqn:
                    source_name = _extract_name_from_fqn(source_fqn)

                    target_fqn = self.indexer.get_symbol_fqn(ref.target_id)
                    target_name = (
                        _extract_name_from_fqn(target_fqn) if target_fqn else "unknown"
                    )

                    references_entries.append(
                        RawReference(
                            name=target_name,
                            kind="call",
                            file=file_path,
                            parent_symbol=source_name,
                        )
                    )

            # 5. Type Relationships
            for tr in facts.type_relationships:
                source_fqn = self.indexer.get_symbol_fqn(tr.source_id)
                if source_fqn and file_path in source_fqn:
                    source_name = _extract_name_from_fqn(source_fqn)

                    target_fqn = self.indexer.get_symbol_fqn(tr.target_id)
                    target_name = (
                        _extract_name_from_fqn(target_fqn) if target_fqn else "unknown"
                    )

                    type_relationships_entries.append(
                        TypeRelationshipEntry(
                            source=source_name,
                            target=target_name,
                            relation_type=tr.relationship_type.value,
                            file=file_path,
                        )
                    )

            # 6. Endpoints
            for ep in facts.endpoints:
                handler_fqn = self.indexer.get_symbol_fqn(ep.symbol_id)
                if handler_fqn and file_path in handler_fqn:
                    handler_name = _extract_name_from_fqn(handler_fqn)
                    route = f"{ep.method.value} {ep.path}"

                    entrypoints_entries.append(
                        EntrypointEntry(
                            route=route,
                            handler=handler_name,
                            kind="rest_endpoint",
                            framework=ep.framework,
                            file=file_path,
                        )
                    )

            # 7. Database/Persistence
            for db in facts.database_relationships:
                sym_fqn = self.indexer.get_symbol_fqn(db.symbol_id)
                if sym_fqn and file_path in sym_fqn:
                    sym_name = _extract_name_from_fqn(sym_fqn)

                    # Distinguish persistence model from custom method
                    persistence_entries.append(
                        PersistenceEntry(
                            name=sym_name,
                            kind="table",
                            file=file_path,
                        )
                    )

            # 8. Events
            for pub in facts.event_publications:
                sym_fqn = self.indexer.get_symbol_fqn(pub.symbol_id)
                if sym_fqn and file_path in sym_fqn:
                    sym_name = _extract_name_from_fqn(sym_fqn)
                    event_entries.append(
                        EventEntry(
                            symbol_name=sym_name,
                            operation_kind=pub.publication_type.value,
                            event_name=f"event_{pub.event_id}",
                            file=file_path,
                        )
                    )
            for sub in facts.event_subscriptions:
                sym_fqn = self.indexer.get_symbol_fqn(sub.symbol_id)
                if sym_fqn and file_path in sym_fqn:
                    sym_name = _extract_name_from_fqn(sym_fqn)
                    event_entries.append(
                        EventEntry(
                            symbol_name=sym_name,
                            operation_kind=sub.subscription_type.value,
                            event_name=f"event_{sub.event_id}",
                            file=file_path,
                        )
                    )

            # 9. Tests
            for test_rel in facts.test_relationships:
                test_fqn = self.indexer.get_symbol_fqn(test_rel.test_symbol_id)
                if test_fqn and file_path in test_fqn:
                    test_name = _extract_name_from_fqn(test_fqn)

                    target_fqn = self.indexer.get_symbol_fqn(test_rel.target_symbol_id)
                    target_name = (
                        _extract_name_from_fqn(target_fqn) if target_fqn else ""
                    )

                    test_entries.append(
                        TestEntry(
                            name=test_name,
                            kind="function",
                            file=file_path,
                            metadata={"covers": [target_name]} if target_name else {},
                        )
                    )

            file_indices.append(
                FileIndex(
                    path=file_path,
                    language=language,
                    symbols=tuple(symbols_entries),
                    imports=tuple(imports_entries),
                    references=tuple(references_entries),
                    calls=tuple(calls_entries),
                    entrypoints=tuple(entrypoints_entries),
                    type_relationships=tuple(type_relationships_entries),
                    persistence_models=tuple(persistence_entries),
                    repository_methods=tuple(repository_methods_entries),
                    events=tuple(event_entries),
                    tests=tuple(test_entries),
                )
            )

        return RepositoryIndex(
            files=tuple(file_indices),
            metadata={"language": language},
        )

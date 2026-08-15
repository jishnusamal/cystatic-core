from collections import defaultdict
from typing import Dict, List, Set, Tuple

from engine.repository.query import RepositoryQuery
from engine.repository.facts import (
    Call,
    DatabaseRelationship,
    Endpoint,
    EventId,
    EventPublication,
    EventSubscription,
    File,
    FileId,
    Import,
    Reference,
    Symbol,
    SymbolId,
    TestRelationship,
    TypeRelationship,
)
from engine.repository.model.repository_model import EntryPoint, EntryPointKind
from engine.repository.overlay.overlay import RepositoryOverlay



class RepositoryView(RepositoryQuery):
    """
    Combines a base RepositoryQuery (e.g. SQLiteRepositoryStore or InMemoryRepository)
    with a RepositoryOverlay of changes (additions, removals, modifications).
    
    Provides the same RepositoryQuery interface, delegating and merging results.
    """

    def __init__(self, base: RepositoryQuery, overlay: RepositoryOverlay) -> None:
        self.base = base
        self.overlay = overlay

        # Pre-index added facts by query lookup key
        self._added_calls_from: Dict[SymbolId, List[Call]] = defaultdict(list)
        self._added_calls_to: Dict[SymbolId, List[Call]] = defaultdict(list)
        for c in overlay.added_calls:
            self._added_calls_from[c.caller_id].append(c)
            self._added_calls_to[c.callee_id].append(c)

        self._added_refs_from: Dict[SymbolId, List[Reference]] = defaultdict(list)
        self._added_refs_to: Dict[SymbolId, List[Reference]] = defaultdict(list)
        for r in overlay.added_references:
            self._added_refs_from[r.source_id].append(r)
            self._added_refs_to[r.target_id].append(r)

        self._added_imports_from: Dict[FileId, List[Import]] = defaultdict(list)
        self._added_imports_to: Dict[FileId, List[Import]] = defaultdict(list)
        for i in overlay.added_imports:
            self._added_imports_from[i.source_file_id].append(i)
            if i.target_file_id is not None:
                self._added_imports_to[i.target_file_id].append(i)

        self._added_type_from: Dict[SymbolId, List[TypeRelationship]] = defaultdict(list)
        self._added_type_to: Dict[SymbolId, List[TypeRelationship]] = defaultdict(list)
        for tr in overlay.added_type_relationships:
            self._added_type_from[tr.source_id].append(tr)
            self._added_type_to[tr.target_id].append(tr)

        self._added_endpoints: Dict[SymbolId, List[Endpoint]] = defaultdict(list)
        for ep in overlay.added_endpoints:
            self._added_endpoints[ep.symbol_id].append(ep)

        self._added_db_rels: Dict[SymbolId, List[DatabaseRelationship]] = defaultdict(list)
        for db in overlay.added_database_relationships:
            self._added_db_rels[db.symbol_id].append(db)

        self._added_event_pubs: Dict[SymbolId, List[EventPublication]] = defaultdict(list)
        for pub in overlay.added_event_publications:
            self._added_event_pubs[pub.symbol_id].append(pub)

        self._added_event_subs: Dict[EventId, List[EventSubscription]] = defaultdict(list)
        for sub in overlay.added_event_subscriptions:
            self._added_event_subs[sub.event_id].append(sub)

        self._added_tests: Dict[SymbolId, List[TestRelationship]] = defaultdict(list)
        for t in overlay.added_test_relationships:
            self._added_tests[t.target_symbol_id].append(t)

    def _should_skip_base_for_symbol(self, symbol_id: SymbolId) -> bool:
        if symbol_id in self.overlay.added_symbols:
            return True
        if symbol_id in self.overlay.removed_symbols:
            return True
        base_sym = self.base.get_symbol(symbol_id)
        if base_sym is not None:
            if (base_sym.file_id in self.overlay.modified_files or 
                base_sym.file_id in self.overlay.removed_files):
                return True
        return False

    def get_symbol(self, symbol_id: SymbolId) -> Symbol | None:
        if symbol_id in self.overlay.added_symbols:
            return self.overlay.added_symbols[symbol_id]
        if symbol_id in self.overlay.removed_symbols:
            return None
        
        base_symbol = self.base.get_symbol(symbol_id)
        if base_symbol is not None:
            if (base_symbol.file_id in self.overlay.removed_files or 
                base_symbol.file_id in self.overlay.modified_files):
                return None
            return base_symbol
        return None

    def get_file(self, file_id: FileId) -> File | None:
        if file_id in self.overlay.added_files:
            return self.overlay.added_files[file_id]
        if file_id in self.overlay.removed_files:
            return None
        
        base_file = self.base.get_file(file_id)
        if base_file is not None:
            if base_file.id in self.overlay.modified_files:
                return None
            return base_file
        return None

    def get_callers(self, symbol_id: SymbolId) -> tuple[Call, ...]:
        base_callers = self.base.get_callers(symbol_id)
        v_callers = [
            c for c in base_callers
            if not self._should_skip_base_for_symbol(c.caller_id)
            and self.get_symbol(c.caller_id) is not None 
            and c not in self.overlay.removed_calls
        ]
        return tuple(v_callers + self._added_calls_to.get(symbol_id, []))

    def get_callees(self, symbol_id: SymbolId) -> tuple[Call, ...]:
        if self._should_skip_base_for_symbol(symbol_id) or self.get_symbol(symbol_id) is None:
            return tuple(self._added_calls_from.get(symbol_id, []))
        base_callees = self.base.get_callees(symbol_id)
        v_callees = [
            c for c in base_callees
            if not self._should_skip_base_for_symbol(c.callee_id)
            and self.get_symbol(c.callee_id) is not None 
            and c not in self.overlay.removed_calls
        ]
        return tuple(v_callees + self._added_calls_from.get(symbol_id, []))

    def get_references_from(self, symbol_id: SymbolId) -> tuple[Reference, ...]:
        if self._should_skip_base_for_symbol(symbol_id) or self.get_symbol(symbol_id) is None:
            return tuple(self._added_refs_from.get(symbol_id, []))
        base_refs = self.base.get_references_from(symbol_id)
        v_refs = [
            r for r in base_refs
            if not self._should_skip_base_for_symbol(r.target_id)
            and self.get_symbol(r.target_id) is not None 
            and r not in self.overlay.removed_references
        ]
        return tuple(v_refs + self._added_refs_from.get(symbol_id, []))

    def get_references_to(self, symbol_id: SymbolId) -> tuple[Reference, ...]:
        base_refs = self.base.get_references_to(symbol_id)
        v_refs = [
            r for r in base_refs
            if not self._should_skip_base_for_symbol(r.source_id)
            and self.get_symbol(r.source_id) is not None 
            and r not in self.overlay.removed_references
        ]
        return tuple(v_refs + self._added_refs_to.get(symbol_id, []))

    def get_imports(self, file_id: FileId) -> tuple[Import, ...]:
        if (file_id in self.overlay.modified_files or 
            file_id in self.overlay.removed_files or 
            self.get_file(file_id) is None):
            return tuple(self._added_imports_from.get(file_id, []))
            
        base_imports = self.base.get_imports(file_id)
        v_imports = [
            i for i in base_imports
            if (i.target_file_id is None or (
                i.target_file_id not in self.overlay.removed_files and
                self.get_file(i.target_file_id) is not None
            )) 
            and i not in self.overlay.removed_imports
        ]
        return tuple(v_imports + self._added_imports_from.get(file_id, []))

    def get_importers(self, file_id: FileId) -> tuple[Import, ...]:
        if file_id in self.overlay.removed_files or self.get_file(file_id) is None:
            return ()
        base_importers = self.base.get_importers(file_id)
        v_importers = [
            i for i in base_importers
            if i.source_file_id not in self.overlay.modified_files
            and i.source_file_id not in self.overlay.removed_files
            and self.get_file(i.source_file_id) is not None 
            and i not in self.overlay.removed_imports
        ]
        return tuple(v_importers + self._added_imports_to.get(file_id, []))

    def get_type_relationships(self, symbol_id: SymbolId) -> tuple[TypeRelationship, ...]:
        if self._should_skip_base_for_symbol(symbol_id) or self.get_symbol(symbol_id) is None:
            return tuple(self._added_type_from.get(symbol_id, []))
        base_type_rels = self.base.get_type_relationships(symbol_id)
        v_rels = [
            tr for tr in base_type_rels
            if not self._should_skip_base_for_symbol(tr.target_id)
            and self.get_symbol(tr.target_id) is not None 
            and tr not in self.overlay.removed_type_relationships
        ]
        return tuple(v_rels + self._added_type_from.get(symbol_id, []))

    def get_type_dependents(self, symbol_id: SymbolId) -> tuple[TypeRelationship, ...]:
        base_type_rels = self.base.get_type_dependents(symbol_id)
        v_rels = [
            tr for tr in base_type_rels
            if not self._should_skip_base_for_symbol(tr.source_id)
            and self.get_symbol(tr.source_id) is not None 
            and tr not in self.overlay.removed_type_relationships
        ]
        return tuple(v_rels + self._added_type_to.get(symbol_id, []))

    def get_endpoints(self, symbol_id: SymbolId) -> tuple[Endpoint, ...]:
        if self._should_skip_base_for_symbol(symbol_id) or self.get_symbol(symbol_id) is None:
            return tuple(self._added_endpoints.get(symbol_id, []))
        base_endpoints = self.base.get_endpoints(symbol_id)
        v_endpoints = [
            ep for ep in base_endpoints
            if ep not in self.overlay.removed_endpoints
        ]
        return tuple(v_endpoints + self._added_endpoints.get(symbol_id, []))

    def get_database_relationships(self, symbol_id: SymbolId) -> tuple[DatabaseRelationship, ...]:
        if self._should_skip_base_for_symbol(symbol_id) or self.get_symbol(symbol_id) is None:
            return tuple(self._added_db_rels.get(symbol_id, []))
        base_db_rels = self.base.get_database_relationships(symbol_id)
        v_db_rels = [
            db for db in base_db_rels
            if db not in self.overlay.removed_database_relationships
        ]
        return tuple(v_db_rels + self._added_db_rels.get(symbol_id, []))

    def get_published_events(self, symbol_id: SymbolId) -> tuple[EventPublication, ...]:
        if self._should_skip_base_for_symbol(symbol_id) or self.get_symbol(symbol_id) is None:
            return tuple(self._added_event_pubs.get(symbol_id, []))
        base_pubs = self.base.get_published_events(symbol_id)
        v_pubs = [
            pub for pub in base_pubs
            if pub not in self.overlay.removed_event_publications
        ]
        return tuple(v_pubs + self._added_event_pubs.get(symbol_id, []))

    def get_event_consumers(self, event_id: EventId) -> tuple[EventSubscription, ...]:
        base_subs = self.base.get_event_consumers(event_id)
        v_subs = [
            sub for sub in base_subs
            if not self._should_skip_base_for_symbol(sub.symbol_id)
            and self.get_symbol(sub.symbol_id) is not None 
            and sub not in self.overlay.removed_event_subscriptions
        ]
        return tuple(v_subs + self._added_event_subs.get(event_id, []))

    def get_tests(self, symbol_id: SymbolId) -> tuple[TestRelationship, ...]:
        base_tests = self.base.get_tests(symbol_id)
        v_tests = [
            t for t in base_tests
            if not self._should_skip_base_for_symbol(t.test_symbol_id)
            and self.get_symbol(t.test_symbol_id) is not None 
            and t not in self.overlay.removed_test_relationships
        ]
        return tuple(v_tests + self._added_tests.get(symbol_id, []))

    def get_entry_points(self) -> tuple[EntryPoint, ...]:
        base_eps = self.base.get_entry_points()
        v_eps = []
        for ep in base_eps:
            try:
                sym_id_int = int(ep.handler_id)
                sym_id = SymbolId(sym_id_int)
                if not self._should_skip_base_for_symbol(sym_id) and self.get_symbol(sym_id) is not None:
                    v_eps.append(ep)
            except ValueError:
                v_eps.append(ep)
                
        for ep_list in self._added_endpoints.values():
            for ep in ep_list:
                sym_id_str = str(ep.symbol_id)
                route = f"{ep.method} {ep.path}"
                v_eps.append(EntryPoint(
                    kind=EntryPointKind.REST_ENDPOINT,
                    route=route,
                    handler_id=sym_id_str,
                    metadata={"framework": ep.framework, "method": ep.method, "path": ep.path}
                ))
                
        for sub_list in self._added_event_subs.values():
            for sub in sub_list:
                sym_id_str = str(sub.symbol_id)
                event_id_str = str(sub.event_id)
                v_eps.append(EntryPoint(
                    kind=EntryPointKind.EVENT_CONSUMER,
                    route=f"event:{event_id_str}",
                    handler_id=sym_id_str,
                    metadata={"subscription_type": str(sub.subscription_type), "event_id": event_id_str}
                ))
                
        return tuple(v_eps)


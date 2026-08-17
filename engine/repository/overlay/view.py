from collections import defaultdict

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
from engine.repository.query import QueryResult, RepositoryQuery
from core.config import get_compiler_settings


class RepositoryView(RepositoryQuery):
    """
    Combines a base RepositoryQuery (e.g. SQLiteRepositoryStore or InMemoryRepository)
    with a RepositoryOverlay of changes (additions, removals, modifications).

    Provides the same RepositoryQuery interface, delegating and merging results.
    """

    def __init__(
        self,
        base: RepositoryQuery,
        overlay: RepositoryOverlay,
        resolver = None,
        repository_id: str | None = None,
        commit_sha: str | None = None,
    ) -> None:
        self.base = base
        self.overlay = overlay
        self.resolver = resolver
        self.repository_id = repository_id or getattr(base, "repository_id", None)
        
        # Resolve commit_sha if possible
        version_id = getattr(base, "version_id", None)
        self.commit_sha = commit_sha
        if not self.commit_sha and version_id:
            self.commit_sha = version_id.split("@")[-1]

        self._resolved_requirements = set()

        # Pre-index added facts by query lookup key
        self._added_calls_from: dict[SymbolId, list[Call]] = defaultdict(list)
        self._added_calls_to: dict[SymbolId, list[Call]] = defaultdict(list)
        for c in overlay.added_calls:
            self._added_calls_from[c.caller_id].append(c)
            self._added_calls_to[c.callee_id].append(c)

        self._added_refs_from: dict[SymbolId, list[Reference]] = defaultdict(list)
        self._added_refs_to: dict[SymbolId, list[Reference]] = defaultdict(list)
        for r in overlay.added_references:
            self._added_refs_from[r.source_id].append(r)
            self._added_refs_to[r.target_id].append(r)

        self._added_imports_from: dict[FileId, list[Import]] = defaultdict(list)
        self._added_imports_to: dict[FileId, list[Import]] = defaultdict(list)
        for i in overlay.added_imports:
            self._added_imports_from[i.source_file_id].append(i)
            if i.target_file_id is not None:
                self._added_imports_to[i.target_file_id].append(i)

        self._added_type_from: dict[SymbolId, list[TypeRelationship]] = defaultdict(
            list
        )
        self._added_type_to: dict[SymbolId, list[TypeRelationship]] = defaultdict(list)
        for tr in overlay.added_type_relationships:
            self._added_type_from[tr.source_id].append(tr)
            self._added_type_to[tr.target_id].append(tr)

        self._added_endpoints: dict[SymbolId, list[Endpoint]] = defaultdict(list)
        for ep in overlay.added_endpoints:
            self._added_endpoints[ep.symbol_id].append(ep)

        self._added_db_rels: dict[SymbolId, list[DatabaseRelationship]] = defaultdict(
            list
        )
        for db in overlay.added_database_relationships:
            self._added_db_rels[db.symbol_id].append(db)

        self._added_event_pubs: dict[SymbolId, list[EventPublication]] = defaultdict(
            list
        )
        for pub in overlay.added_event_publications:
            self._added_event_pubs[pub.symbol_id].append(pub)

        self._added_event_subs: dict[EventId, list[EventSubscription]] = defaultdict(
            list
        )
        for sub in overlay.added_event_subscriptions:
            self._added_event_subs[sub.event_id].append(sub)

        self._added_tests: dict[SymbolId, list[TestRelationship]] = defaultdict(list)
        for t in overlay.added_test_relationships:
            self._added_tests[t.target_symbol_id].append(t)

    def _resolve_if_needed(self, result, requirement) -> bool:
        # Respect the global lazy‑resolution feature flag
        from core.config import get_compiler_settings
        if not get_compiler_settings().ENABLE_LAZY_REPOSITORY_RESOLUTION:
            return False
        if requirement in self._resolved_requirements:
            return False
        if not result.complete and self.resolver and self.repository_id and self.commit_sha:
            self._resolved_requirements.add(requirement)
            self.resolver.resolve_sync(self.repository_id, self.commit_sha, [requirement])
            return True
        return False

    def _get_unresolved_symbol_id(self, symbol_name: str) -> SymbolId | None:
        if self.resolver and hasattr(self.resolver, "materializer") and hasattr(self.resolver.materializer, "indexer"):
            indexer = self.resolver.materializer.indexer
            fqn = f"unresolved://{symbol_name}"
            if fqn in indexer._symbol_id_map:
                return indexer._symbol_id_map[fqn]
        return None

    def _resolve_unresolved_symbol_id(self, unresolved_id: SymbolId) -> SymbolId:
        if self.resolver and hasattr(self.resolver, "materializer") and hasattr(self.resolver.materializer, "indexer"):
            indexer = self.resolver.materializer.indexer
            fqn = indexer._symbol_fqn_map.get(unresolved_id)
            if fqn and fqn.startswith("unresolved://"):
                name = fqn[len("unresolved://"):]
                if hasattr(self.base, "conn"):
                    cur = self.base.conn.cursor()
                    repo_id = self.repository_id or ""
                    version_id = ""
                    if hasattr(self.base, "_get_context"):
                        try:
                            _, version_id = self.base._get_context()
                        except Exception:
                            pass
                    cur.execute(
                        "SELECT id FROM symbols WHERE name = ? AND repository_id = ? AND version_id = ? LIMIT 1",
                        (name, repo_id, version_id),
                    )
                    row = cur.fetchone()
                    if row:
                        return SymbolId(row[0])
        return unresolved_id

    def _should_skip_base_for_symbol(self, symbol_id: SymbolId) -> bool:
        if symbol_id in self.overlay.added_symbols:
            return True
        if symbol_id in self.overlay.removed_symbols:
            return True
        base_sym = self.base.get_symbol(symbol_id)
        if base_sym is not None:
            if (
                base_sym.file_id in self.overlay.modified_files
                or base_sym.file_id in self.overlay.removed_files
            ):
                return True
        return False

    def get_symbol(self, symbol_id: SymbolId) -> Symbol | None:
        if symbol_id in self.overlay.added_symbols:
            return self.overlay.added_symbols[symbol_id]
        if symbol_id in self.overlay.removed_symbols:
            return None

        base_symbol = self.base.get_symbol(symbol_id)
        if base_symbol is not None:
            if (
                base_symbol.file_id in self.overlay.removed_files
                or base_symbol.file_id in self.overlay.modified_files
            ):
                return None
            return base_symbol
        return None

    def _is_symbol_changed(self, symbol_id: SymbolId) -> bool:
        if symbol_id in self.overlay.added_symbols or symbol_id in self.overlay.removed_symbols:
            return True
        base_sym = self.base.get_symbol(symbol_id)
        if base_sym is not None:
            if (
                base_sym.file_id in self.overlay.modified_files
                or base_sym.file_id in self.overlay.removed_files
            ):
                return True
        return False

    def get_symbols(self, symbol_ids: list[SymbolId]) -> QueryResult[Symbol]:
        added_syms = []
        base_sym_ids = []
        for sid in symbol_ids:
            if sid in self.overlay.added_symbols:
                added_syms.append(self.overlay.added_symbols[sid])
            elif sid in self.overlay.removed_symbols:
                pass
            else:
                base_sym_ids.append(sid)

        base_res = self.base.get_symbols(base_sym_ids)
        filtered_base_syms = []
        for sym in base_res.facts:
            if (
                sym.file_id in self.overlay.removed_files
                or sym.file_id in self.overlay.modified_files
            ):
                continue
            filtered_base_syms.append(sym)

        res = QueryResult(tuple(added_syms) + tuple(filtered_base_syms), complete=base_res.complete)
        
        from engine.repository.resolver.requirements import SymbolResolutionRequirement
        reqs = [SymbolResolutionRequirement(sid, "symbols") for sid in base_sym_ids]
        
        unresolved_reqs = [r for r in reqs if r not in self._resolved_requirements]
        if not res.complete and unresolved_reqs and self.resolver and self.repository_id and self.commit_sha:
            for r in unresolved_reqs:
                self._resolved_requirements.add(r)
            self.resolver.resolve_sync(self.repository_id, self.commit_sha, unresolved_reqs)
            return self.get_symbols(symbol_ids)
            
        if any(r in self._resolved_requirements for r in reqs):
            return QueryResult(res.facts, complete=True)
            
        return res

    def get_file(self, file_id: FileId) -> File | None:
        if file_id in self.overlay.added_files:
            return self.overlay.added_files[file_id]
        for f in self.overlay.added_files.values():
            if f.path == file_id:
                return f
        if file_id in self.overlay.removed_files:
            return None

        base_file = self.base.get_file(file_id)
        if base_file is not None:
            if (
                base_file.id in self.overlay.modified_files
                or base_file.id in self.overlay.removed_files
            ):
                return None
            return base_file
        return None

    def get_callers(self, symbol_id: SymbolId) -> QueryResult[Call]:
        base_res = self.base.get_callers(symbol_id)
        facts = list(base_res.facts)
        symbol = self.get_symbol(symbol_id)
        if symbol:
            unresolved_id = self._get_unresolved_symbol_id(symbol.name)
            if unresolved_id and unresolved_id != symbol_id:
                unresolved_res = self.base.get_callers(unresolved_id)
                for c in unresolved_res.facts:
                    mapped_call = Call(
                        caller_id=c.caller_id,
                        callee_id=symbol_id,
                        call_type=c.call_type
                    )
                    if mapped_call not in facts:
                        facts.append(mapped_call)

        v_callers = [
            c
            for c in facts
            if not self._should_skip_base_for_symbol(c.caller_id)
            and self.get_symbol(c.caller_id) is not None
            and c not in self.overlay.removed_calls
        ]
        res = QueryResult(tuple(v_callers + self._added_calls_to.get(symbol_id, [])), complete=base_res.complete)
        from engine.repository.resolver.requirements import SymbolResolutionRequirement
        req = SymbolResolutionRequirement(symbol_id, "callers")
        if self._resolve_if_needed(res, req):
            return self.get_callers(symbol_id)
        if req in self._resolved_requirements:
            return QueryResult(res.facts, complete=True)
        return res

    def get_callees(self, symbol_id: SymbolId) -> QueryResult[Call]:
        if (
            self._should_skip_base_for_symbol(symbol_id)
            or self.get_symbol(symbol_id) is None
        ):
            return QueryResult(tuple(self._added_calls_from.get(symbol_id, [])), complete=True)
        base_res = self.base.get_callees(symbol_id)
        v_callees = []
        for c in base_res.facts:
            if not self._should_skip_base_for_symbol(c.callee_id) and c not in self.overlay.removed_calls:
                resolved_callee_id = self._resolve_unresolved_symbol_id(c.callee_id)
                if self.get_symbol(resolved_callee_id) is not None:
                    v_callees.append(Call(c.caller_id, resolved_callee_id, c.call_type))

        complete = True if self._is_symbol_changed(symbol_id) else base_res.complete
        res = QueryResult(tuple(v_callees + self._added_calls_from.get(symbol_id, [])), complete=complete)
        from engine.repository.resolver.requirements import SymbolResolutionRequirement
        req = SymbolResolutionRequirement(symbol_id, "callees")
        if self._resolve_if_needed(res, req):
            return self.get_callees(symbol_id)
        if req in self._resolved_requirements:
            return QueryResult(res.facts, complete=True)
        return res

    def get_references_from(self, symbol_id: SymbolId) -> QueryResult[Reference]:
        if (
            self._should_skip_base_for_symbol(symbol_id)
            or self.get_symbol(symbol_id) is None
        ):
            return QueryResult(tuple(self._added_refs_from.get(symbol_id, [])), complete=True)
        base_res = self.base.get_references_from(symbol_id)
        v_refs = []
        for r in base_res.facts:
            if not self._should_skip_base_for_symbol(r.target_id) and r not in self.overlay.removed_references:
                resolved_target_id = self._resolve_unresolved_symbol_id(r.target_id)
                if self.get_symbol(resolved_target_id) is not None:
                    v_refs.append(Reference(r.source_id, resolved_target_id, r.relation_type))

        complete = True if self._is_symbol_changed(symbol_id) else base_res.complete
        res = QueryResult(tuple(v_refs + self._added_refs_from.get(symbol_id, [])), complete=complete)
        from engine.repository.resolver.requirements import SymbolResolutionRequirement
        req = SymbolResolutionRequirement(symbol_id, "references_from")
        if self._resolve_if_needed(res, req):
            return self.get_references_from(symbol_id)
        if req in self._resolved_requirements:
            return QueryResult(res.facts, complete=True)
        return res

    def get_references_to(self, symbol_id: SymbolId) -> QueryResult[Reference]:
        base_res = self.base.get_references_to(symbol_id)
        facts = list(base_res.facts)
        symbol = self.get_symbol(symbol_id)
        if symbol:
            unresolved_id = self._get_unresolved_symbol_id(symbol.name)
            if unresolved_id and unresolved_id != symbol_id:
                unresolved_res = self.base.get_references_to(unresolved_id)
                for r in unresolved_res.facts:
                    mapped_ref = Reference(
                        source_id=r.source_id,
                        target_id=symbol_id,
                        relation_type=r.relation_type
                    )
                    if mapped_ref not in facts:
                        facts.append(mapped_ref)

        v_refs = [
            r
            for r in facts
            if not self._should_skip_base_for_symbol(r.source_id)
            and self.get_symbol(r.source_id) is not None
            and r not in self.overlay.removed_references
        ]
        res = QueryResult(tuple(v_refs + self._added_refs_to.get(symbol_id, [])), complete=base_res.complete)
        from engine.repository.resolver.requirements import SymbolResolutionRequirement
        req = SymbolResolutionRequirement(symbol_id, "references_to")
        if self._resolve_if_needed(res, req):
            return self.get_references_to(symbol_id)
        if req in self._resolved_requirements:
            return QueryResult(res.facts, complete=True)
        return res

    def get_imports(self, file_id: FileId) -> QueryResult[Import]:
        if (
            file_id in self.overlay.modified_files
            or file_id in self.overlay.removed_files
            or self.get_file(file_id) is None
        ):
            return QueryResult(tuple(self._added_imports_from.get(file_id, [])), complete=True)

        base_res = self.base.get_imports(file_id)
        v_imports = [
            i
            for i in base_res.facts
            if (
                i.target_file_id is None
                or (
                    i.target_file_id not in self.overlay.removed_files
                    and self.get_file(i.target_file_id) is not None
                )
            )
            and i not in self.overlay.removed_imports
        ]
        complete = True if (file_id in self.overlay.added_files or file_id in self.overlay.modified_files) else base_res.complete
        res = QueryResult(tuple(v_imports + self._added_imports_from.get(file_id, [])), complete=complete)
        from engine.repository.resolver.requirements import FileResolutionRequirement
        req = FileResolutionRequirement(file_id, "file")
        if self._resolve_if_needed(res, req):
            return self.get_imports(file_id)
        if req in self._resolved_requirements:
            return QueryResult(res.facts, complete=True)
        return res

    def get_importers(self, file_id: FileId) -> QueryResult[Import]:
        if file_id in self.overlay.removed_files or self.get_file(file_id) is None:
            return QueryResult((), complete=True)
        base_res = self.base.get_importers(file_id)
        v_importers = [
            i
            for i in base_res.facts
            if i.source_file_id not in self.overlay.modified_files
            and i.source_file_id not in self.overlay.removed_files
            and self.get_file(i.source_file_id) is not None
            and i not in self.overlay.removed_imports
        ]
        res = QueryResult(tuple(v_importers + self._added_imports_to.get(file_id, [])), complete=base_res.complete)
        from engine.repository.resolver.requirements import FileResolutionRequirement
        req = FileResolutionRequirement(file_id, "importers")
        if self._resolve_if_needed(res, req):
            return self.get_importers(file_id)
        if req in self._resolved_requirements:
            return QueryResult(res.facts, complete=True)
        return res

    def get_type_relationships(
        self, symbol_id: SymbolId
    ) -> QueryResult[TypeRelationship]:
        if (
            self._should_skip_base_for_symbol(symbol_id)
            or self.get_symbol(symbol_id) is None
        ):
            return QueryResult(tuple(self._added_type_from.get(symbol_id, [])), complete=True)
        base_res = self.base.get_type_relationships(symbol_id)
        v_rels = []
        for tr in base_res.facts:
            if not self._should_skip_base_for_symbol(tr.target_id) and tr not in self.overlay.removed_type_relationships:
                resolved_target_id = self._resolve_unresolved_symbol_id(tr.target_id)
                if self.get_symbol(resolved_target_id) is not None:
                    v_rels.append(TypeRelationship(tr.source_id, resolved_target_id, tr.relation_type))

        complete = True if self._is_symbol_changed(symbol_id) else base_res.complete
        res = QueryResult(tuple(v_rels + self._added_type_from.get(symbol_id, [])), complete=complete)
        from engine.repository.resolver.requirements import SymbolResolutionRequirement
        req = SymbolResolutionRequirement(symbol_id, "type_relationships")
        if self._resolve_if_needed(res, req):
            return self.get_type_relationships(symbol_id)
        if req in self._resolved_requirements:
            return QueryResult(res.facts, complete=True)
        return res

    def get_type_dependents(self, symbol_id: SymbolId) -> QueryResult[TypeRelationship]:
        base_res = self.base.get_type_dependents(symbol_id)
        facts = list(base_res.facts)
        symbol = self.get_symbol(symbol_id)
        if symbol:
            unresolved_id = self._get_unresolved_symbol_id(symbol.name)
            if unresolved_id and unresolved_id != symbol_id:
                unresolved_res = self.base.get_type_dependents(unresolved_id)
                for tr in unresolved_res.facts:
                    mapped_tr = TypeRelationship(
                        source_id=tr.source_id,
                        target_id=symbol_id,
                        relation_type=tr.relation_type
                    )
                    if mapped_tr not in facts:
                        facts.append(mapped_tr)

        v_rels = [
            tr
            for tr in facts
            if not self._should_skip_base_for_symbol(tr.source_id)
            and self.get_symbol(tr.source_id) is not None
            and tr not in self.overlay.removed_type_relationships
        ]
        res = QueryResult(tuple(v_rels + self._added_type_to.get(symbol_id, [])), complete=base_res.complete)
        from engine.repository.resolver.requirements import SymbolResolutionRequirement
        req = SymbolResolutionRequirement(symbol_id, "type_dependents")
        if self._resolve_if_needed(res, req):
            return self.get_type_dependents(symbol_id)
        if req in self._resolved_requirements:
            return QueryResult(res.facts, complete=True)
        return res

    def get_endpoints(self, symbol_id: SymbolId) -> QueryResult[Endpoint]:
        if (
            self._should_skip_base_for_symbol(symbol_id)
            or self.get_symbol(symbol_id) is None
        ):
            return QueryResult(tuple(self._added_endpoints.get(symbol_id, [])), complete=True)
        base_res = self.base.get_endpoints(symbol_id)
        v_endpoints = [
            ep for ep in base_res.facts if ep not in self.overlay.removed_endpoints
        ]
        complete = True if self._is_symbol_changed(symbol_id) else base_res.complete
        res = QueryResult(tuple(v_endpoints + self._added_endpoints.get(symbol_id, [])), complete=complete)
        from engine.repository.resolver.requirements import SymbolResolutionRequirement
        req = SymbolResolutionRequirement(symbol_id, "endpoints")
        if self._resolve_if_needed(res, req):
            return self.get_endpoints(symbol_id)
        if req in self._resolved_requirements:
            return QueryResult(res.facts, complete=True)
        return res

    def get_database_relationships(
        self, symbol_id: SymbolId
    ) -> QueryResult[DatabaseRelationship]:
        if (
            self._should_skip_base_for_symbol(symbol_id)
            or self.get_symbol(symbol_id) is None
        ):
            return QueryResult(tuple(self._added_db_rels.get(symbol_id, [])), complete=True)
        base_res = self.base.get_database_relationships(symbol_id)
        v_db_rels = [
            db
            for db in base_res.facts
            if db not in self.overlay.removed_database_relationships
        ]
        complete = True if self._is_symbol_changed(symbol_id) else base_res.complete
        res = QueryResult(tuple(v_db_rels + self._added_db_rels.get(symbol_id, [])), complete=complete)
        from engine.repository.resolver.requirements import SymbolResolutionRequirement
        req = SymbolResolutionRequirement(symbol_id, "database_relationships")
        if self._resolve_if_needed(res, req):
            return self.get_database_relationships(symbol_id)
        if req in self._resolved_requirements:
            return QueryResult(res.facts, complete=True)
        return res

    def get_published_events(self, symbol_id: SymbolId) -> QueryResult[EventPublication]:
        if (
            self._should_skip_base_for_symbol(symbol_id)
            or self.get_symbol(symbol_id) is None
        ):
            return QueryResult(tuple(self._added_event_pubs.get(symbol_id, [])), complete=True)
        base_res = self.base.get_published_events(symbol_id)
        v_pubs = [
            pub
            for pub in base_res.facts
            if pub not in self.overlay.removed_event_publications
        ]
        complete = True if self._is_symbol_changed(symbol_id) else base_res.complete
        res = QueryResult(tuple(v_pubs + self._added_event_pubs.get(symbol_id, [])), complete=complete)
        from engine.repository.resolver.requirements import SymbolResolutionRequirement
        req = SymbolResolutionRequirement(symbol_id, "published_events")
        if self._resolve_if_needed(res, req):
            return self.get_published_events(symbol_id)
        if req in self._resolved_requirements:
            return QueryResult(res.facts, complete=True)
        return res

    def get_event_consumers(self, event_id: EventId) -> QueryResult[EventSubscription]:
        base_res = self.base.get_event_consumers(event_id)
        v_subs = [
            sub
            for sub in base_res.facts
            if not self._should_skip_base_for_symbol(sub.symbol_id)
            and self.get_symbol(sub.symbol_id) is not None
            and sub not in self.overlay.removed_event_subscriptions
        ]
        res = QueryResult(tuple(v_subs + self._added_event_subs.get(event_id, [])), complete=base_res.complete)
        from engine.repository.resolver.requirements import EventResolutionRequirement
        req = EventResolutionRequirement(event_id)
        if self._resolve_if_needed(res, req):
            return self.get_event_consumers(event_id)
        if req in self._resolved_requirements:
            return QueryResult(res.facts, complete=True)
        return res

    def get_tests(self, symbol_id: SymbolId) -> QueryResult[TestRelationship]:
        base_res = self.base.get_tests(symbol_id)
        v_tests = [
            t
            for t in base_res.facts
            if not self._should_skip_base_for_symbol(t.test_symbol_id)
            and self.get_symbol(t.test_symbol_id) is not None
            and t not in self.overlay.removed_test_relationships
        ]
        res = QueryResult(tuple(v_tests + self._added_tests.get(symbol_id, [])), complete=base_res.complete)
        from engine.repository.resolver.requirements import SymbolResolutionRequirement
        req = SymbolResolutionRequirement(symbol_id, "tests")
        if self._resolve_if_needed(res, req):
            return self.get_tests(symbol_id)
        if req in self._resolved_requirements:
            return QueryResult(res.facts, complete=True)
        return res

    def get_entry_points(self) -> QueryResult[EntryPoint]:
        base_res = self.base.get_entry_points()
        v_eps = []
        for ep in base_res.facts:
            try:
                sym_id_int = int(ep.handler_id)
                sym_id = SymbolId(sym_id_int)
                if (
                    not self._should_skip_base_for_symbol(sym_id)
                    and self.get_symbol(sym_id) is not None
                ):
                    v_eps.append(ep)
            except ValueError:
                v_eps.append(ep)

        for ep_list in self._added_endpoints.values():
            for ep in ep_list:
                sym_id_str = str(ep.symbol_id)
                route = f"{ep.method} {ep.path}"
                v_eps.append(
                    EntryPoint(
                        kind=EntryPointKind.REST_ENDPOINT,
                        route=route,
                        handler_id=sym_id_str,
                        metadata={
                            "framework": ep.framework,
                            "method": ep.method,
                            "path": ep.path,
                        },
                    )
                )

        for sub_list in self._added_event_subs.values():
            for sub in sub_list:
                sym_id_str = str(sub.symbol_id)
                event_id_str = str(sub.event_id)
                v_eps.append(
                    EntryPoint(
                        kind=EntryPointKind.EVENT_CONSUMER,
                        route=f"event:{event_id_str}",
                        handler_id=sym_id_str,
                        metadata={
                            "subscription_type": str(sub.subscription_type),
                            "event_id": event_id_str,
                        },
                    )
                )

        res = QueryResult(tuple(v_eps), complete=base_res.complete)
        from engine.repository.resolver.requirements import AllEntryPointsRequirement
        req = AllEntryPointsRequirement()
        if self._resolve_if_needed(res, req):
            return self.get_entry_points()
        if req in self._resolved_requirements:
            return QueryResult(res.facts, complete=True)
        return res

    def get_symbols_in_file(self, file_id: FileId) -> QueryResult[Symbol]:
        if file_id in self.overlay.removed_files and file_id not in self.overlay.modified_files:
            return QueryResult((), complete=True)

        if (
            file_id in self.overlay.added_files
            or file_id in self.overlay.modified_files
        ):
            added_syms = [
                s for s in self.overlay.added_symbols.values() if s.file_id == file_id
            ]
            return QueryResult(tuple(added_syms), complete=True)

        base_res = self.base.get_symbols_in_file(file_id)
        res = QueryResult(tuple(s for s in base_res.facts if s.id not in self.overlay.removed_symbols), complete=base_res.complete)
        from engine.repository.resolver.requirements import FileResolutionRequirement
        req = FileResolutionRequirement(file_id, "symbols")
        if self._resolve_if_needed(res, req):
            return self.get_symbols_in_file(file_id)
        if req in self._resolved_requirements:
            return QueryResult(res.facts, complete=True)
        return res

from collections import defaultdict

from engine.repository.facts import RepositoryFacts
from engine.repository.model.repository_model import EntryPoint, EntryPointKind

from .repository import RepositoryQuery
from .types import (
    Call,
    DatabaseRelationship,
    Endpoint,
    EventId,
    EventPublication,
    EventSubscription,
    File,
    FileId,
    Import,
    QueryResult,
    Reference,
    Symbol,
    SymbolId,
    TestRelationship,
    TypeRelationship,
)


class InMemoryRepository(RepositoryQuery):
    """
    In-memory adapter implementing the RepositoryQuery interface using RepositoryFacts.
    """

    def __init__(self, facts: RepositoryFacts, complete: bool = True):
        self._facts = facts
        self.complete = complete

        # Precompute reverse indexes not present in RepositoryFacts for O(1) lookups
        self._importers: dict[FileId, tuple[Import, ...]] = {}
        importers_map = defaultdict(list)
        for imp in facts.imports:
            if imp.target_file_id is not None:
                importers_map[imp.target_file_id].append(imp)
        self._importers = {k: tuple(v) for k, v in importers_map.items()}

        self._type_dependents: dict[SymbolId, tuple[TypeRelationship, ...]] = {}
        dependents_map = defaultdict(list)
        for tr in facts.type_relationships:
            dependents_map[tr.target_id].append(tr)
        self._type_dependents = {k: tuple(v) for k, v in dependents_map.items()}

    def get_symbol(self, symbol_id: SymbolId) -> Symbol | None:
        return self._facts.get_symbol(symbol_id)

    def get_file(self, file_id: FileId) -> File | None:
        return self._facts.get_file(file_id)

    def get_callers(self, symbol_id: SymbolId) -> QueryResult[Call]:
        return QueryResult(self._facts.calls_to(symbol_id), complete=self.complete)

    def get_callees(self, symbol_id: SymbolId) -> QueryResult[Call]:
        return QueryResult(self._facts.calls_from(symbol_id), complete=self.complete)

    def get_references_from(self, symbol_id: SymbolId) -> QueryResult[Reference]:
        return QueryResult(self._facts.references_from(symbol_id), complete=self.complete)

    def get_references_to(self, symbol_id: SymbolId) -> QueryResult[Reference]:
        return QueryResult(self._facts.references_to(symbol_id), complete=self.complete)

    def get_imports(self, file_id: FileId) -> QueryResult[Import]:
        return QueryResult(self._facts.imports_from(file_id), complete=self.complete)

    def get_importers(self, file_id: FileId) -> QueryResult[Import]:
        return QueryResult(self._importers.get(file_id, ()), complete=self.complete)

    def get_type_relationships(
        self, symbol_id: SymbolId
    ) -> QueryResult[TypeRelationship]:
        return QueryResult(self._facts.type_relationships_from(symbol_id), complete=self.complete)

    def get_type_dependents(self, symbol_id: SymbolId) -> QueryResult[TypeRelationship]:
        return QueryResult(self._type_dependents.get(symbol_id, ()), complete=self.complete)

    def get_endpoints(self, symbol_id: SymbolId) -> QueryResult[Endpoint]:
        return QueryResult(self._facts.endpoints_for(symbol_id), complete=self.complete)

    def get_database_relationships(
        self, symbol_id: SymbolId
    ) -> QueryResult[DatabaseRelationship]:
        return QueryResult(self._facts.database_relationships_for(symbol_id), complete=self.complete)

    def get_published_events(self, symbol_id: SymbolId) -> QueryResult[EventPublication]:
        return QueryResult(self._facts.publications_for(symbol_id), complete=self.complete)

    def get_event_consumers(self, event_id: EventId) -> QueryResult[EventSubscription]:
        return QueryResult(self._facts.subscriptions_for(event_id), complete=self.complete)

    def get_tests(self, symbol_id: SymbolId) -> QueryResult[TestRelationship]:
        return QueryResult(self._facts.tests_for(symbol_id), complete=self.complete)

    def get_entry_points(self) -> QueryResult[EntryPoint]:
        entry_points = []

        for ep in self._facts.endpoints:
            entry_points.append(
                EntryPoint(
                    kind=EntryPointKind.REST_ENDPOINT,
                    route=f"{ep.method} {ep.path}",
                    handler_id=str(ep.symbol_id),
                    metadata={
                        "framework": ep.framework,
                        "method": ep.method,
                        "path": ep.path,
                    },
                )
            )

        for sub in self._facts.event_subscriptions:
            entry_points.append(
                EntryPoint(
                    kind=EntryPointKind.EVENT_CONSUMER,
                    route=f"event:{sub.event_id}",
                    handler_id=str(sub.symbol_id),
                    metadata={
                        "subscription_type": sub.subscription_type,
                        "event_id": sub.event_id,
                    },
                )
            )

        return QueryResult(tuple(entry_points), complete=self.complete)

    def get_symbols_in_file(self, file_id: FileId) -> QueryResult[Symbol]:
        return QueryResult(tuple(s for s in self._facts.symbols if s.file_id == file_id), complete=self.complete)


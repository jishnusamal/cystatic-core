from abc import ABC, abstractmethod

from engine.repository.model.repository_model import EntryPoint

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


class RepositoryQuery(ABC):
    """
    Abstract interface for querying repository facts.
    """

    @abstractmethod
    def get_symbol(self, symbol_id: SymbolId) -> Symbol | None:
        """Fetch a symbol by its ID."""

    def get_symbols(self, symbol_ids: list[SymbolId]) -> QueryResult[Symbol]:
        """Fetch multiple symbols by their IDs."""
        results = []
        for sid in symbol_ids:
            sym = self.get_symbol(sid)
            if sym is not None:
                results.append(sym)
        return QueryResult(tuple(results), complete=True)

    @abstractmethod
    def get_file(self, file_id: FileId) -> File | None:
        """Fetch a file by its ID."""

    @abstractmethod
    def get_callers(self, symbol_id: SymbolId) -> QueryResult[Call]:
        """Fetch calls targeting the given symbol."""

    @abstractmethod
    def get_callees(self, symbol_id: SymbolId) -> QueryResult[Call]:
        """Fetch calls initiated from the given symbol."""

    @abstractmethod
    def get_references_from(self, symbol_id: SymbolId) -> QueryResult[Reference]:
        """Fetch references originating from the given symbol."""

    @abstractmethod
    def get_references_to(self, symbol_id: SymbolId) -> QueryResult[Reference]:
        """Fetch references targeting the given symbol."""

    @abstractmethod
    def get_imports(self, file_id: FileId) -> QueryResult[Import]:
        """Fetch imports declared inside the given file."""

    @abstractmethod
    def get_importers(self, file_id: FileId) -> QueryResult[Import]:
        """Fetch imports targeting the given file."""

    @abstractmethod
    def get_type_relationships(
        self, symbol_id: SymbolId
    ) -> QueryResult[TypeRelationship]:
        """Fetch type relationships where the symbol is the source."""

    @abstractmethod
    def get_type_dependents(self, symbol_id: SymbolId) -> QueryResult[TypeRelationship]:
        """Fetch type relationships where the symbol is the target."""

    @abstractmethod
    def get_endpoints(self, symbol_id: SymbolId) -> QueryResult[Endpoint]:
        """Fetch HTTP endpoints exposed by the given symbol."""

    @abstractmethod
    def get_database_relationships(
        self, symbol_id: SymbolId
    ) -> QueryResult[DatabaseRelationship]:
        """Fetch database resource relationships associated with the symbol."""

    @abstractmethod
    def get_published_events(self, symbol_id: SymbolId) -> QueryResult[EventPublication]:
        """Fetch event publications emitted by the symbol."""

    @abstractmethod
    def get_event_consumers(self, event_id: EventId) -> QueryResult[EventSubscription]:
        """Fetch subscriptions handling the given event ID."""

    @abstractmethod
    def get_tests(self, symbol_id: SymbolId) -> QueryResult[TestRelationship]:
        """Fetch test relationships targeting the given code symbol ID."""

    @abstractmethod
    def get_entry_points(self) -> QueryResult[EntryPoint]:
        """Fetch all recognized entry points in the repository."""

    @abstractmethod
    def get_symbols_in_file(self, file_id: FileId) -> QueryResult[Symbol]:
        """Fetch all symbols contained in the given file."""


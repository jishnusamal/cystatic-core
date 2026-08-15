from abc import ABC, abstractmethod
from typing import Any
from .types import (
    Call,
    DatabaseRelationship,
    Endpoint,
    EventPublication,
    EventSubscription,
    File,
    FileId,
    Import,
    Reference,
    Symbol,
    SymbolId,
    EventId,
    TestRelationship,
    TypeRelationship,
)
from engine.repository.model.repository_model import EntryPoint


class RepositoryQuery(ABC):
    """
    Abstract interface for querying repository facts.
    """

    @abstractmethod
    def get_symbol(self, symbol_id: SymbolId) -> Symbol | None:
        """Fetch a symbol by its ID."""
        pass

    @abstractmethod
    def get_file(self, file_id: FileId) -> File | None:
        """Fetch a file by its ID."""
        pass

    @abstractmethod
    def get_callers(self, symbol_id: SymbolId) -> tuple[Call, ...]:
        """Fetch calls targeting the given symbol."""
        pass

    @abstractmethod
    def get_callees(self, symbol_id: SymbolId) -> tuple[Call, ...]:
        """Fetch calls initiated from the given symbol."""
        pass

    @abstractmethod
    def get_references_from(self, symbol_id: SymbolId) -> tuple[Reference, ...]:
        """Fetch references originating from the given symbol."""
        pass

    @abstractmethod
    def get_references_to(self, symbol_id: SymbolId) -> tuple[Reference, ...]:
        """Fetch references targeting the given symbol."""
        pass

    @abstractmethod
    def get_imports(self, file_id: FileId) -> tuple[Import, ...]:
        """Fetch imports declared inside the given file."""
        pass

    @abstractmethod
    def get_importers(self, file_id: FileId) -> tuple[Import, ...]:
        """Fetch imports targeting the given file."""
        pass

    @abstractmethod
    def get_type_relationships(
        self, symbol_id: SymbolId
    ) -> tuple[TypeRelationship, ...]:
        """Fetch type relationships where the symbol is the source."""
        pass

    @abstractmethod
    def get_type_dependents(self, symbol_id: SymbolId) -> tuple[TypeRelationship, ...]:
        """Fetch type relationships where the symbol is the target."""
        pass

    @abstractmethod
    def get_endpoints(self, symbol_id: SymbolId) -> tuple[Endpoint, ...]:
        """Fetch HTTP endpoints exposed by the given symbol."""
        pass

    @abstractmethod
    def get_database_relationships(
        self, symbol_id: SymbolId
    ) -> tuple[DatabaseRelationship, ...]:
        """Fetch database resource relationships associated with the symbol."""
        pass

    @abstractmethod
    def get_published_events(self, symbol_id: SymbolId) -> tuple[EventPublication, ...]:
        """Fetch event publications emitted by the symbol."""
        pass

    @abstractmethod
    def get_event_consumers(self, event_id: EventId) -> tuple[EventSubscription, ...]:
        """Fetch subscriptions handling the given event ID."""
        pass

    @abstractmethod
    def get_tests(self, symbol_id: SymbolId) -> tuple[TestRelationship, ...]:
        """Fetch test relationships targeting the given code symbol ID."""
        pass

    @abstractmethod
    def get_entry_points(self) -> tuple[EntryPoint, ...]:
        """Fetch all recognized entry points in the repository."""
        pass

    @abstractmethod
    def get_symbols_in_file(self, file_id: FileId) -> tuple[Symbol, ...]:
        """Fetch all symbols contained in the given file."""
        pass

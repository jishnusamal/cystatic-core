from abc import ABC, abstractmethod
from engine.repository.facts import (
    FileId,
    SymbolId,
    File,
    Symbol,
    Call,
    Reference,
    Import,
    TypeRelationship,
    Endpoint,
    DatabaseRelationship,
    EventPublication,
    EventSubscription,
    TestRelationship,
    RepositoryFacts,
)


class RepositoryFactSink(ABC):
    """
    Abstract interface for streaming facts from the repository indexer.
    
    The indexer writes facts sequentially to the sink without accumulating
    them in memory.
    """

    @abstractmethod
    def add_file(self, file: File) -> FileId:
        """Add a source file fact to the sink."""
        pass

    @abstractmethod
    def add_symbol(self, symbol: Symbol) -> SymbolId:
        """Add a code symbol fact to the sink."""
        pass

    @abstractmethod
    def add_call(self, call: Call) -> None:
        """Add a call dependency fact to the sink."""
        pass

    @abstractmethod
    def add_reference(self, reference: Reference) -> None:
        """Add a reference fact to the sink."""
        pass

    @abstractmethod
    def add_import(self, import_fact: Import) -> None:
        """Add an import fact to the sink."""
        pass

    @abstractmethod
    def add_type_relationship(self, type_rel: TypeRelationship) -> None:
        """Add a type relationship fact to the sink."""
        pass

    @abstractmethod
    def add_endpoint(self, endpoint: Endpoint) -> None:
        """Add an endpoint fact to the sink."""
        pass

    @abstractmethod
    def add_database_relationship(self, db_rel: DatabaseRelationship) -> None:
        """Add a database relationship fact to the sink."""
        pass

    @abstractmethod
    def add_event_publication(self, pub: EventPublication) -> None:
        """Add an event publication fact to the sink."""
        pass

    @abstractmethod
    def add_event_subscription(self, sub: EventSubscription) -> None:
        """Add an event subscription fact to the sink."""
        pass

    @abstractmethod
    def add_test_relationship(self, test_rel: TestRelationship) -> None:
        """Add a test relationship fact to the sink."""
        pass


class InMemoryFactSink(RepositoryFactSink):
    """
    In-memory implementation of RepositoryFactSink.
    
    Accumulates all facts in memory for testing and easy validation/compilation.
    """

    def __init__(self) -> None:
        self.files: list[File] = []
        self.symbols: list[Symbol] = []
        self.calls: list[Call] = []
        self.references: list[Reference] = []
        self.imports: list[Import] = []
        self.type_relationships: list[TypeRelationship] = []
        self.endpoints: list[Endpoint] = []
        self.database_relationships: list[DatabaseRelationship] = []
        self.event_publications: list[EventPublication] = []
        self.event_subscriptions: list[EventSubscription] = []
        self.test_relationships: list[TestRelationship] = []

    def add_file(self, file: File) -> FileId:
        self.files.append(file)
        return file.id

    def add_symbol(self, symbol: Symbol) -> SymbolId:
        self.symbols.append(symbol)
        return symbol.id

    def add_call(self, call: Call) -> None:
        self.calls.append(call)

    def add_reference(self, reference: Reference) -> None:
        self.references.append(reference)

    def add_import(self, import_fact: Import) -> None:
        self.imports.append(import_fact)

    def add_type_relationship(self, type_rel: TypeRelationship) -> None:
        self.type_relationships.append(type_rel)

    def add_endpoint(self, endpoint: Endpoint) -> None:
        self.endpoints.append(endpoint)

    def add_database_relationship(self, db_rel: DatabaseRelationship) -> None:
        self.database_relationships.append(db_rel)

    def add_event_publication(self, pub: EventPublication) -> None:
        self.event_publications.append(pub)

    def add_event_subscription(self, sub: EventSubscription) -> None:
        self.event_subscriptions.append(sub)

    def add_test_relationship(self, test_rel: TestRelationship) -> None:
        self.test_relationships.append(test_rel)

    def build_facts(self) -> RepositoryFacts:
        """Consolidate the accumulated flat facts into an immutable RepositoryFacts object."""
        return RepositoryFacts(
            files=tuple(self.files),
            symbols=tuple(self.symbols),
            calls=tuple(self.calls),
            references=tuple(self.references),
            imports=tuple(self.imports),
            type_relationships=tuple(self.type_relationships),
            endpoints=tuple(self.endpoints),
            database_relationships=tuple(self.database_relationships),
            event_publications=tuple(self.event_publications),
            event_subscriptions=tuple(self.event_subscriptions),
            test_relationships=tuple(self.test_relationships),
        )

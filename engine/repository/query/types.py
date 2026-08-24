from dataclasses import dataclass

from engine.repository.facts import (
    Call,
    CallType,
    DatabaseRelationship,
    DatabaseRelationshipType,
    Endpoint,
    EndpointId,
    EndpointMethod,
    EventId,
    EventPublication,
    EventPublicationType,
    EventSubscription,
    EventSubscriptionType,
    File,
    FileId,
    Import,
    ImportType,
    Reference,
    ReferenceType,
    ResourceId,
    Symbol,
    SymbolId,
    SymbolKind,
    SymbolVisibility,
    TestRelationship,
    TestRelationshipType,
    TypeRelationship,
    TypeRelationshipType,
)


@dataclass(frozen=True)
class QueryResult[T]:
    """
    Wrapper for repository query results that couples the facts found with
    a completeness flag indicating if the relevant repository scope has been fully materialized.
    """

    facts: tuple[T, ...]
    complete: bool

    def __iter__(self):
        return iter(self.facts)

    def __len__(self) -> int:
        return len(self.facts)

    def __getitem__(self, index):
        return self.facts[index]

    def __eq__(self, other: object) -> bool:
        if isinstance(other, QueryResult):
            return self.facts == other.facts and self.complete == other.complete
        if isinstance(other, (tuple, list)):
            return self.facts == tuple(other)
        return False


__all__ = [
    "Call",
    "CallType",
    "DatabaseRelationship",
    "DatabaseRelationshipType",
    "Endpoint",
    "EndpointId",
    "EndpointMethod",
    "EventId",
    "EventPublication",
    "EventPublicationType",
    "EventSubscription",
    "EventSubscriptionType",
    "File",
    "FileId",
    "Import",
    "ImportType",
    "QueryResult",
    "Reference",
    "ReferenceType",
    "ResourceId",
    "Symbol",
    "SymbolId",
    "SymbolKind",
    "SymbolVisibility",
    "TestRelationship",
    "TestRelationshipType",
    "TypeRelationship",
    "TypeRelationshipType",
]


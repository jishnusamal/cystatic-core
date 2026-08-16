from dataclasses import dataclass, field

from engine.repository.facts import (
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
    TestRelationship,
    TypeRelationship,
)


@dataclass(frozen=True)
class RepositoryOverlay:
    """
    Immutable representation of the repository fact changes introduced in a PR.
    """

    added_files: dict[FileId, File] = field(default_factory=dict)
    removed_files: set[FileId] = field(default_factory=set)
    modified_files: set[FileId] = field(default_factory=set)

    added_symbols: dict[SymbolId, Symbol] = field(default_factory=dict)
    removed_symbols: set[SymbolId] = field(default_factory=set)

    added_calls: set[Call] = field(default_factory=set)
    removed_calls: set[Call] = field(default_factory=set)

    added_references: set[Reference] = field(default_factory=set)
    removed_references: set[Reference] = field(default_factory=set)

    added_imports: set[Import] = field(default_factory=set)
    removed_imports: set[Import] = field(default_factory=set)

    added_type_relationships: set[TypeRelationship] = field(default_factory=set)
    removed_type_relationships: set[TypeRelationship] = field(default_factory=set)

    added_endpoints: set[Endpoint] = field(default_factory=set)
    removed_endpoints: set[Endpoint] = field(default_factory=set)

    added_database_relationships: set[DatabaseRelationship] = field(default_factory=set)
    removed_database_relationships: set[DatabaseRelationship] = field(
        default_factory=set
    )

    added_event_publications: set[EventPublication] = field(default_factory=set)
    removed_event_publications: set[EventPublication] = field(default_factory=set)

    added_event_subscriptions: set[EventSubscription] = field(default_factory=set)
    removed_event_subscriptions: set[EventSubscription] = field(default_factory=set)

    added_test_relationships: set[TestRelationship] = field(default_factory=set)
    removed_test_relationships: set[TestRelationship] = field(default_factory=set)

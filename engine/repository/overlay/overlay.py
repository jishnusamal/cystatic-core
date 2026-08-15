from dataclasses import dataclass, field
from typing import Set, Dict, Tuple
from engine.repository.facts import (
    File, FileId, Symbol, SymbolId, Call, Reference, Import,
    TypeRelationship, Endpoint, DatabaseRelationship,
    EventPublication, EventSubscription, TestRelationship
)

@dataclass(frozen=True)
class RepositoryOverlay:
    """
    Immutable representation of the repository fact changes introduced in a PR.
    """
    added_files: Dict[FileId, File] = field(default_factory=dict)
    removed_files: Set[FileId] = field(default_factory=set)
    modified_files: Set[FileId] = field(default_factory=set)

    added_symbols: Dict[SymbolId, Symbol] = field(default_factory=dict)
    removed_symbols: Set[SymbolId] = field(default_factory=set)

    added_calls: Set[Call] = field(default_factory=set)
    removed_calls: Set[Call] = field(default_factory=set)

    added_references: Set[Reference] = field(default_factory=set)
    removed_references: Set[Reference] = field(default_factory=set)

    added_imports: Set[Import] = field(default_factory=set)
    removed_imports: Set[Import] = field(default_factory=set)

    added_type_relationships: Set[TypeRelationship] = field(default_factory=set)
    removed_type_relationships: Set[TypeRelationship] = field(default_factory=set)

    added_endpoints: Set[Endpoint] = field(default_factory=set)
    removed_endpoints: Set[Endpoint] = field(default_factory=set)

    added_database_relationships: Set[DatabaseRelationship] = field(default_factory=set)
    removed_database_relationships: Set[DatabaseRelationship] = field(default_factory=set)

    added_event_publications: Set[EventPublication] = field(default_factory=set)
    removed_event_publications: Set[EventPublication] = field(default_factory=set)

    added_event_subscriptions: Set[EventSubscription] = field(default_factory=set)
    removed_event_subscriptions: Set[EventSubscription] = field(default_factory=set)

    added_test_relationships: Set[TestRelationship] = field(default_factory=set)
    removed_test_relationships: Set[TestRelationship] = field(default_factory=set)

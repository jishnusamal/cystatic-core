from collections import defaultdict
from dataclasses import dataclass, field
from typing import Mapping

from .ids import FileId, SymbolId, EventId, ResourceId, EndpointId
from .file import File
from .symbol import Symbol
from .call import Call
from .reference import Reference
from .imports import Import
from .type_relationship import TypeRelationship
from .endpoint import Endpoint
from .database import DatabaseRelationship
from .event import EventPublication, EventSubscription
from .test import TestRelationship


@dataclass(frozen=True)
class RepositoryFacts:
    """
    Flat collection of all repository facts.
    
    Computes lookups and indexes in __post_init__ to serve query APIs.
    """
    files: tuple[File, ...] = field(default_factory=tuple)
    symbols: tuple[Symbol, ...] = field(default_factory=tuple)
    calls: tuple[Call, ...] = field(default_factory=tuple)
    references: tuple[Reference, ...] = field(default_factory=tuple)
    imports: tuple[Import, ...] = field(default_factory=tuple)
    type_relationships: tuple[TypeRelationship, ...] = field(default_factory=tuple)
    endpoints: tuple[Endpoint, ...] = field(default_factory=tuple)
    database_relationships: tuple[DatabaseRelationship, ...] = field(default_factory=tuple)
    event_publications: tuple[EventPublication, ...] = field(default_factory=tuple)
    event_subscriptions: tuple[EventSubscription, ...] = field(default_factory=tuple)
    test_relationships: tuple[TestRelationship, ...] = field(default_factory=tuple)

    # In-memory indexes computed on post_init
    _file_map: dict[FileId, File] = field(default_factory=dict, init=False, repr=False, compare=False)
    _symbol_map: dict[SymbolId, Symbol] = field(default_factory=dict, init=False, repr=False, compare=False)
    
    _calls_from: dict[SymbolId, tuple[Call, ...]] = field(default_factory=dict, init=False, repr=False, compare=False)
    _calls_to: dict[SymbolId, tuple[Call, ...]] = field(default_factory=dict, init=False, repr=False, compare=False)
    
    _references_from: dict[SymbolId, tuple[Reference, ...]] = field(default_factory=dict, init=False, repr=False, compare=False)
    _references_to: dict[SymbolId, tuple[Reference, ...]] = field(default_factory=dict, init=False, repr=False, compare=False)
    
    _imports_from: dict[FileId, tuple[Import, ...]] = field(default_factory=dict, init=False, repr=False, compare=False)
    
    _type_relationships_from: dict[SymbolId, tuple[TypeRelationship, ...]] = field(default_factory=dict, init=False, repr=False, compare=False)
    _endpoints_for: dict[SymbolId, tuple[Endpoint, ...]] = field(default_factory=dict, init=False, repr=False, compare=False)
    
    _database_relationships_for: dict[SymbolId, tuple[DatabaseRelationship, ...]] = field(default_factory=dict, init=False, repr=False, compare=False)
    
    _publications_for: dict[SymbolId, tuple[EventPublication, ...]] = field(default_factory=dict, init=False, repr=False, compare=False)
    _subscriptions_for: dict[EventId, tuple[EventSubscription, ...]] = field(default_factory=dict, init=False, repr=False, compare=False)
    
    _tests_for: dict[SymbolId, tuple[TestRelationship, ...]] = field(default_factory=dict, init=False, repr=False, compare=False)

    def __post_init__(self):
        # Enforce all collections are tuples
        for field_name in (
            "files", "symbols", "calls", "references", "imports", 
            "type_relationships", "endpoints", "database_relationships",
            "event_publications", "event_subscriptions", "test_relationships"
        ):
            val = getattr(self, field_name)
            if not isinstance(val, tuple):
                object.__setattr__(self, field_name, tuple(val))

        # Build maps
        object.__setattr__(self, '_file_map', {f.id: f for f in self.files})
        object.__setattr__(self, '_symbol_map', {s.id: s for s in self.symbols})

        # Build call lookup indexes
        calls_from = defaultdict(list)
        calls_to = defaultdict(list)
        for c in self.calls:
            calls_from[c.caller_id].append(c)
            calls_to[c.callee_id].append(c)
        object.__setattr__(self, '_calls_from', {k: tuple(v) for k, v in calls_from.items()})
        object.__setattr__(self, '_calls_to', {k: tuple(v) for k, v in calls_to.items()})

        # Build reference lookup indexes
        refs_from = defaultdict(list)
        refs_to = defaultdict(list)
        for r in self.references:
            refs_from[r.source_id].append(r)
            refs_to[r.target_id].append(r)
        object.__setattr__(self, '_references_from', {k: tuple(v) for k, v in refs_from.items()})
        object.__setattr__(self, '_references_to', {k: tuple(v) for k, v in refs_to.items()})

        # Build import lookup indexes
        imports_from = defaultdict(list)
        for i in self.imports:
            imports_from[i.source_file_id].append(i)
        object.__setattr__(self, '_imports_from', {k: tuple(v) for k, v in imports_from.items()})

        # Build type relationship lookup indexes
        tr_from = defaultdict(list)
        for tr in self.type_relationships:
            tr_from[tr.source_id].append(tr)
        object.__setattr__(self, '_type_relationships_from', {k: tuple(v) for k, v in tr_from.items()})

        # Build endpoints lookup indexes
        eps = defaultdict(list)
        for ep in self.endpoints:
            eps[ep.symbol_id].append(ep)
        object.__setattr__(self, '_endpoints_for', {k: tuple(v) for k, v in eps.items()})

        # Build database relationships lookup indexes
        db_rels = defaultdict(list)
        for db in self.database_relationships:
            db_rels[db.symbol_id].append(db)
        object.__setattr__(self, '_database_relationships_for', {k: tuple(v) for k, v in db_rels.items()})

        # Build event publications lookup indexes
        pub_rels = defaultdict(list)
        for pub in self.event_publications:
            pub_rels[pub.symbol_id].append(pub)
        object.__setattr__(self, '_publications_for', {k: tuple(v) for k, v in pub_rels.items()})

        # Build event subscriptions lookup indexes
        sub_rels = defaultdict(list)
        for sub in self.event_subscriptions:
            sub_rels[sub.event_id].append(sub)
        object.__setattr__(self, '_subscriptions_for', {k: tuple(v) for k, v in sub_rels.items()})

        # Build test relationships lookup indexes targeting a code symbol
        test_rels = defaultdict(list)
        for t in self.test_relationships:
            test_rels[t.target_symbol_id].append(t)
        object.__setattr__(self, '_tests_for', {k: tuple(v) for k, v in test_rels.items()})

    def get_symbol(self, symbol_id: SymbolId) -> Symbol | None:
        """Fetch a symbol by its ID."""
        return self._symbol_map.get(symbol_id)

    def get_file(self, file_id: FileId) -> File | None:
        """Fetch a file by its ID."""
        return self._file_map.get(file_id)

    def calls_from(self, symbol_id: SymbolId) -> tuple[Call, ...]:
        """Fetch all calls initiated from the given symbol."""
        return self._calls_from.get(symbol_id, ())

    def calls_to(self, symbol_id: SymbolId) -> tuple[Call, ...]:
        """Fetch all calls targeting the given symbol."""
        return self._calls_to.get(symbol_id, ())

    def references_from(self, symbol_id: SymbolId) -> tuple[Reference, ...]:
        """Fetch references originating from the given symbol."""
        return self._references_from.get(symbol_id, ())

    def references_to(self, symbol_id: SymbolId) -> tuple[Reference, ...]:
        """Fetch references targeting the given symbol."""
        return self._references_to.get(symbol_id, ())

    def imports_from(self, file_id: FileId) -> tuple[Import, ...]:
        """Fetch imports declared inside the given file."""
        return self._imports_from.get(file_id, ())

    def type_relationships_from(self, symbol_id: SymbolId) -> tuple[TypeRelationship, ...]:
        """Fetch type relationships where the symbol is the source."""
        return self._type_relationships_from.get(symbol_id, ())

    def endpoints_for(self, symbol_id: SymbolId) -> tuple[Endpoint, ...]:
        """Fetch HTTP endpoints exposed by the given symbol."""
        return self._endpoints_for.get(symbol_id, ())

    def database_relationships_for(self, symbol_id: SymbolId) -> tuple[DatabaseRelationship, ...]:
        """Fetch database resource relationships associated with the symbol."""
        return self._database_relationships_for.get(symbol_id, ())

    def publications_for(self, symbol_id: SymbolId) -> tuple[EventPublication, ...]:
        """Fetch event publications emitted by the symbol."""
        return self._publications_for.get(symbol_id, ())

    def subscriptions_for(self, event_id: EventId) -> tuple[EventSubscription, ...]:
        """Fetch subscriptions handling the given event ID."""
        return self._subscriptions_for.get(event_id, ())

    def tests_for(self, symbol_id: SymbolId) -> tuple[TestRelationship, ...]:
        """Fetch test relationships targeting the given code symbol ID."""
        return self._tests_for.get(symbol_id, ())

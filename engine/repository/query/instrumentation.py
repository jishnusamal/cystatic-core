import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from engine.repository.model.repository_model import EntryPoint

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
    Reference,
    Symbol,
    SymbolId,
    TestRelationship,
    TypeRelationship,
)


@dataclass
class QueryStats:
    query_name: str
    calls: int = 0
    results: int = 0
    total_latency_ms: float = 0.0
    max_latency_ms: float = 0.0

    @property
    def avg_latency_ms(self) -> float:
        if self.calls == 0:
            return 0.0
        return self.total_latency_ms / self.calls


class QueryInstrumenter:
    """
    Manages and records statistics for repository queries.
    """

    def __init__(self):
        self._stats: dict[str, QueryStats] = {}

    def record(self, query_name: str, result_count: int, latency_ms: float):
        if query_name not in self._stats:
            self._stats[query_name] = QueryStats(query_name=query_name)

        stats = self._stats[query_name]
        stats.calls += 1
        stats.results += result_count
        stats.total_latency_ms += latency_ms
        stats.max_latency_ms = max(stats.max_latency_ms, latency_ms)

    def get_stats(self, query_name: str) -> QueryStats | None:
        return self._stats.get(query_name)

    def get_all_stats(self) -> dict[str, QueryStats]:
        return dict(self._stats)

    def reset(self):
        self._stats.clear()


class InstrumentedRepository(RepositoryQuery):
    """
    Decorator/wrapper that instruments any RepositoryQuery instance.
    """

    def __init__(self, delegate: RepositoryQuery, instrumenter: QueryInstrumenter):
        self._delegate = delegate
        self._instrumenter = instrumenter

    def _execute_instrumented(
        self, query_name: str, query_fn: Callable[[], Any]
    ) -> Any:
        start_time = time.perf_counter()
        result = query_fn()
        end_time = time.perf_counter()

        latency_ms = (end_time - start_time) * 1000.0

        # Calculate result count
        if result is None:
            count = 0
        elif isinstance(result, tuple):
            count = len(result)
        else:
            count = 1

        self._instrumenter.record(query_name, count, latency_ms)
        return result

    def get_symbol(self, symbol_id: SymbolId) -> Symbol | None:
        return self._execute_instrumented(
            "get_symbol", lambda: self._delegate.get_symbol(symbol_id)
        )

    def get_file(self, file_id: FileId) -> File | None:
        return self._execute_instrumented(
            "get_file", lambda: self._delegate.get_file(file_id)
        )

    def get_callers(self, symbol_id: SymbolId) -> tuple[Call, ...]:
        return self._execute_instrumented(
            "get_callers", lambda: self._delegate.get_callers(symbol_id)
        )

    def get_callees(self, symbol_id: SymbolId) -> tuple[Call, ...]:
        return self._execute_instrumented(
            "get_callees", lambda: self._delegate.get_callees(symbol_id)
        )

    def get_references_from(self, symbol_id: SymbolId) -> tuple[Reference, ...]:
        return self._execute_instrumented(
            "get_references_from", lambda: self._delegate.get_references_from(symbol_id)
        )

    def get_references_to(self, symbol_id: SymbolId) -> tuple[Reference, ...]:
        return self._execute_instrumented(
            "get_references_to", lambda: self._delegate.get_references_to(symbol_id)
        )

    def get_imports(self, file_id: FileId) -> tuple[Import, ...]:
        return self._execute_instrumented(
            "get_imports", lambda: self._delegate.get_imports(file_id)
        )

    def get_importers(self, file_id: FileId) -> tuple[Import, ...]:
        return self._execute_instrumented(
            "get_importers", lambda: self._delegate.get_importers(file_id)
        )

    def get_type_relationships(
        self, symbol_id: SymbolId
    ) -> tuple[TypeRelationship, ...]:
        return self._execute_instrumented(
            "get_type_relationships",
            lambda: self._delegate.get_type_relationships(symbol_id),
        )

    def get_type_dependents(self, symbol_id: SymbolId) -> tuple[TypeRelationship, ...]:
        return self._execute_instrumented(
            "get_type_dependents", lambda: self._delegate.get_type_dependents(symbol_id)
        )

    def get_endpoints(self, symbol_id: SymbolId) -> tuple[Endpoint, ...]:
        return self._execute_instrumented(
            "get_endpoints", lambda: self._delegate.get_endpoints(symbol_id)
        )

    def get_database_relationships(
        self, symbol_id: SymbolId
    ) -> tuple[DatabaseRelationship, ...]:
        return self._execute_instrumented(
            "get_database_relationships",
            lambda: self._delegate.get_database_relationships(symbol_id),
        )

    def get_published_events(self, symbol_id: SymbolId) -> tuple[EventPublication, ...]:
        return self._execute_instrumented(
            "get_published_events",
            lambda: self._delegate.get_published_events(symbol_id),
        )

    def get_event_consumers(self, event_id: EventId) -> tuple[EventSubscription, ...]:
        return self._execute_instrumented(
            "get_event_consumers", lambda: self._delegate.get_event_consumers(event_id)
        )

    def get_tests(self, symbol_id: SymbolId) -> tuple[TestRelationship, ...]:
        return self._execute_instrumented(
            "get_tests", lambda: self._delegate.get_tests(symbol_id)
        )

    def get_entry_points(self) -> tuple[EntryPoint, ...]:
        return self._execute_instrumented(
            "get_entry_points", lambda: self._delegate.get_entry_points()
        )

    def get_symbols_in_file(self, file_id: FileId) -> tuple[Symbol, ...]:
        return self._execute_instrumented(
            "get_symbols_in_file", lambda: self._delegate.get_symbols_in_file(file_id)
        )

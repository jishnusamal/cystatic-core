from engine.behavior.compiler.impact_engine import ImpactEngine, TraversalConfig
from engine.repository.model.repository_model import EntryPoint, EntryPointKind
from engine.repository.query.repository import RepositoryQuery
from engine.repository.query.types import (
    Call,
    CallType,
    EventId,
    EventPublication,
    EventPublicationType,
    QueryResult,
    SymbolId,
)


class MockRepositoryQuery(RepositoryQuery):
    def get_symbol(self, symbol_id):
        return None

    def get_file(self, file_id):
        return None

    def get_calls_from(self, caller_id):
        return QueryResult((), complete=True)

    def get_calls_to(self, callee_id):
        # Mock upward traversal: A calls B
        if str(callee_id) == "python://test.py::B":
            return QueryResult(
                (
                    Call(
                        caller_id=SymbolId("python://test.py::A"),
                        callee_id=SymbolId("python://test.py::B"),
                        call_type=CallType.DIRECT,
                    ),
                ),
                complete=True,
            )
        return QueryResult((), complete=True)

    def get_callees(self, caller_id):
        # Mock downward traversal: B calls C
        if str(caller_id) == "python://test.py::B":
            return QueryResult(
                (
                    Call(
                        caller_id=SymbolId("python://test.py::B"),
                        callee_id=SymbolId("python://test.py::C"),
                        call_type=CallType.DIRECT,
                    ),
                ),
                complete=True,
            )
        return QueryResult((), complete=True)

    def get_callers(self, callee_id):
        return self.get_calls_to(callee_id)

    def get_references_to(self, target_id):
        return QueryResult((), complete=True)

    def get_references_from(self, source_id):
        return QueryResult((), complete=True)

    def get_imports_from(self, file_id):
        return QueryResult((), complete=True)

    def get_imports_to(self, file_id):
        return QueryResult((), complete=True)

    def get_implementations(self, symbol_id):
        return QueryResult((), complete=True)

    def get_usages(self, symbol_id):
        return QueryResult((), complete=True)

    def get_endpoints(self, symbol_id):
        return QueryResult((), complete=True)

    def get_database_relationships(self, symbol_id):
        return QueryResult((), complete=True)

    def get_published_events(self, symbol_id):
        if str(symbol_id) == "python://test.py::C":
            return QueryResult(
                (
                    EventPublication(
                        symbol_id=SymbolId("python://test.py::C"),
                        event_id=EventId("event1"),
                        publication_type=EventPublicationType.EMIT,
                    ),
                ),
                complete=True,
            )
        return QueryResult((), complete=True)

    def get_event_consumers(self, event_id):
        return QueryResult((), complete=True)

    def get_tests(self, symbol_id):
        return QueryResult((), complete=True)

    def get_importers(self, symbol_id):
        return QueryResult((), complete=True)

    def get_imports(self, file_id):
        return QueryResult((), complete=True)

    def get_type_dependents(self, symbol_id):
        return QueryResult((), complete=True)

    def get_type_relationships(self, symbol_id):
        return QueryResult((), complete=True)

    def get_symbols_in_file(self, file_id):
        return QueryResult((), complete=True)

    def get_entry_points(self):
        return QueryResult(
            (
                EntryPoint(
                    kind=EntryPointKind.REST_ENDPOINT,
                    route="GET /a",
                    handler_id="python://test.py::A",
                ),
            ),
            complete=True,
        )


def test_impact_engine_basic():
    engine = ImpactEngine(config=TraversalConfig(max_depth=5))
    query = MockRepositoryQuery()

    # Change B
    changed_ids = {"python://test.py::B"}

    surface = engine.calculate_impact(changed_ids, query)

    # Assert
    assert "python://test.py::A" in surface.affected_symbols
    assert "python://test.py::B" in surface.affected_symbols
    assert "python://test.py::C" in surface.affected_symbols

    assert len(surface.affected_endpoints) == 1
    assert next(iter(surface.affected_endpoints)).handler_id == "python://test.py::A"

    assert len(surface.affected_events) == 1
    assert next(iter(surface.affected_events)).symbol_id == "python://test.py::C"

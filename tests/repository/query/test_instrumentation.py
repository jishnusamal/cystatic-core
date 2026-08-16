from engine.repository.facts import (
    File,
    FileId,
    RepositoryFacts,
    Symbol,
    SymbolId,
    SymbolKind,
)
from engine.repository.query import (
    InMemoryRepository,
    InstrumentedRepository,
    QueryInstrumenter,
)


def test_query_instrumentation():
    # 1. Setup simple repository
    file_a = File(id=FileId(1), path="app.py", language="python")
    symbol_a = Symbol(
        id=SymbolId(1),
        name="A",
        file_id=file_a.id,
        kind=SymbolKind.FUNCTION,
        language="python",
        start_line=1,
        end_line=10,
    )
    facts = RepositoryFacts(
        files=(file_a,),
        symbols=(symbol_a,),
    )
    repo = InMemoryRepository(facts)

    # 2. Setup instrumenter and decorate repository
    instrumenter = QueryInstrumenter()
    instrumented_repo = InstrumentedRepository(repo, instrumenter)

    # 3. Perform queries
    assert instrumented_repo.get_symbol(SymbolId(1)) == symbol_a
    assert instrumented_repo.get_symbol(SymbolId(2)) is None

    assert instrumented_repo.get_file(FileId(1)) == file_a
    assert instrumented_repo.get_callers(SymbolId(1)) == ()

    # 4. Verify stats
    stats_get_symbol = instrumenter.get_stats("get_symbol")
    assert stats_get_symbol is not None
    assert stats_get_symbol.calls == 2
    assert stats_get_symbol.results == 1  # 1 for SymbolId(1), 0 for SymbolId(2)
    assert stats_get_symbol.total_latency_ms >= 0.0
    assert stats_get_symbol.max_latency_ms >= 0.0
    assert stats_get_symbol.avg_latency_ms >= 0.0

    stats_get_file = instrumenter.get_stats("get_file")
    assert stats_get_file is not None
    assert stats_get_file.calls == 1
    assert stats_get_file.results == 1

    stats_get_callers = instrumenter.get_stats("get_callers")
    assert stats_get_callers is not None
    assert stats_get_callers.calls == 1
    assert stats_get_callers.results == 0

    all_stats = instrumenter.get_all_stats()
    assert len(all_stats) == 3
    assert "get_symbol" in all_stats
    assert "get_file" in all_stats
    assert "get_callers" in all_stats

    # Reset and verify
    instrumenter.reset()
    assert len(instrumenter.get_all_stats()) == 0

import time

from engine.language.python.adapter import PythonLanguageAdapter
from engine.repository.model import (
    CallEdge,
    CallGraph,
    RepositoryGraph,
)


def test_lazy_indexes():
    # Test 1 — Lazy indexes
    edges = (
        CallEdge(caller_id="foo", callee_id="bar", file="a.py"),
        CallEdge(caller_id="bar", callee_id="baz", file="a.py"),
    )
    cg = CallGraph(edges=edges)

    # Assert outgoing/incoming not materialized yet
    assert "outgoing" not in cg._indexes
    assert "incoming" not in cg._indexes

    # Request outgoing / incoming
    outgoing = cg.outgoing
    incoming = cg.incoming

    # Assert they are now materialized
    assert "outgoing" in cg._indexes
    assert "incoming" in cg._indexes
    assert len(outgoing) == 2
    assert len(incoming) == 2


def test_outgoing_correctness():
    # Test 2 — Correctness: eager outgoing vs lazy outgoing
    edges = (
        CallEdge(caller_id="foo", callee_id="bar", file="a.py"),
        CallEdge(caller_id="bar", callee_id="baz", file="a.py"),
        CallEdge(caller_id="foo", callee_id="baz", file="a.py"),
    )
    cg = CallGraph(edges=edges)

    # Compute eager outgoing manually
    eager_outgoing = {}
    for edge in edges:
        eager_outgoing.setdefault(edge.caller_id, []).append(edge)
    eager_outgoing = {k: tuple(v) for k, v in eager_outgoing.items()}

    # Assert lazy outgoing equals eager outgoing
    assert cg.outgoing == eager_outgoing


def test_incoming_correctness():
    # Test 3 — Incoming correctness
    edges = (
        CallEdge(caller_id="foo", callee_id="bar", file="a.py"),
        CallEdge(caller_id="bar", callee_id="baz", file="a.py"),
        CallEdge(caller_id="foo", callee_id="baz", file="a.py"),
    )
    cg = CallGraph(edges=edges)

    # Compute eager incoming manually
    eager_incoming = {}
    for edge in edges:
        eager_incoming.setdefault(edge.callee_id, []).append(edge)
    eager_incoming = {k: tuple(v) for k, v in eager_incoming.items()}

    # Assert lazy incoming equals eager incoming
    assert cg.incoming == eager_incoming


def test_cache_reuse():
    # Test 4 — Cache reuse
    edges = (CallEdge(caller_id="foo", callee_id="bar", file="a.py"),)
    cg = CallGraph(edges=edges)

    out1 = cg.outgoing
    out2 = cg.outgoing
    out3 = cg.outgoing

    # Assert same object identity is returned (no rebuilding)
    assert id(out1) == id(out2) == id(out3)


def test_invalidation():
    # Test 5 — Invalidation
    graph = RepositoryGraph()
    # Materialize symbol_to_callers initially
    callers1 = graph.symbol_to_callers
    assert graph._indexes.symbol_to_callers is not None

    # Invalidate / patch graph simulation
    graph.invalidate_after_patch()
    assert graph._indexes.symbol_to_callers is None

    # Query again (materialize new index)
    callers2 = graph.symbol_to_callers
    assert graph._indexes.symbol_to_callers is not None


def test_incremental_compiler_equivalence():
    # Test 6 — Incremental compiler equivalence
    base_source_files = {
        "module_a.py": "def foo(): pass",
        "module_b.py": "from module_a import foo\ndef bar(): foo()",
    }
    adapter = PythonLanguageAdapter()
    base_graph = adapter.compile_graph({"files": base_source_files})

    head_source_files = dict(base_source_files)
    head_source_files["module_b.py"] = (
        "from module_a import foo\ndef bar(): foo()\n# comment"
    )

    # Full compilation model
    full_model = adapter.compile({"files": head_source_files})

    # Incremental compilation model
    inc_graph = adapter.compile_incremental(base_graph, {"files": head_source_files})
    inc_model = inc_graph.to_model()

    assert set(inc_model.symbols) == set(full_model.symbols)
    assert set(inc_model.call_graph.edges) == set(full_model.call_graph.edges)
    assert set(inc_model.reference_graph.edges) == set(full_model.reference_graph.edges)


def test_performance_guard():
    # Test 7 — Performance guard (e.g. GraphPatcher must not regress)
    base_source_files = {
        "module_a.py": "def foo(): pass",
        "module_b.py": "from module_a import foo\ndef bar(): foo()",
    }
    adapter = PythonLanguageAdapter()
    base_graph = adapter.compile_graph({"files": base_source_files})

    head_source_files = dict(base_source_files)
    head_source_files["module_b.py"] = (
        "from module_a import foo\ndef bar(): foo()\n# comment"
    )

    t0 = time.perf_counter()
    inc_graph = adapter.compile_incremental(base_graph, {"files": head_source_files})
    duration = time.perf_counter() - t0

    # Ensure incremental compile duration is well within threshold (e.g. < 1.0 second)
    assert duration < 1.0, (
        f"Incremental patching regressed in performance: {duration:.3f}s"
    )

"""Additional tests for LLMContext Reduction: §4 Dead-String Elimination,
§9 Chain Compression, §10-11 Discovery-Centred Filtering, §12 Validation.
"""
from __future__ import annotations

from typing import Any

import pytest

from engine.review_context.model import (
    ReviewContext,
    ChangeContext,
    ChangeSummary,
    FileChange,
    Change,
    SymbolRef,
    ExecutionContext,
    EntryPointExecution,
    ExecutionStep,
    SymbolReference,
    ReachedComponents,
    DeepestExecution,
    Discovery,
    Reference,
)
from engine.llm_context.compiler import LLMContextCompiler
from engine.llm_context.model import LLMContext, StringTable, ExecutionGraph
from engine.llm_context.model import ENUM_REVERSE


# ---------------------------------------------------------------------------
# Re-use helper from existing test module
# ---------------------------------------------------------------------------

from test_llm_context_compiler import TestHelper


def _make_step(
    sym_id: str,
    sym_name: str,
    depth: int,
    changed: bool = False,
    reaches_service: str = "",
) -> ExecutionStep:
    return ExecutionStep(
        behavior=f"behavior://test/{sym_name}",
        symbol=SymbolReference(
            id=sym_id,
            name=sym_name,
            kind="function",
            location=f"app.py:{depth + 1}-{depth + 5}",
        ),
        kind="function",
        depth=depth,
        changed=changed,
        shared=False,
        reaches=ReachedComponents(service=reaches_service, module="", package=""),
        references=(),
    )


def _collect_live_indices(result: LLMContext) -> set[int]:
    """Collect all string table indices referenced by any emitted section."""
    live: set[int] = {0}
    for path_idx, _ in result.f:
        live.add(path_idx)
    for _, name_idx, _ in result.sym:
        if name_idx != 0:
            live.add(name_idx)
    for _, path_idx in result.ep:
        live.add(path_idx)
    for _, _, svc_idx, mod_idx in result.eg.nodes:
        if svc_idx:
            live.add(svc_idx)
        if mod_idx:
            live.add(mod_idx)
    for _, _, term_idx, _ in result.epts:
        if term_idx:
            live.add(term_idx)
    return live


# ---------------------------------------------------------------------------
# Dead-String Elimination (§4)
# ---------------------------------------------------------------------------

class TestDeadStringElimination:

    def test_all_string_indices_are_live(self):
        """Every index 0..n-1 must be referenced by at least one emitted object."""
        step = TestHelper.create_execution_step(
            symbol_id="sym://domain/pay",
            symbol_name="PaymentService",
            symbol_kind="class",
            depth=0,
            changed=True,
            reaches_service="payment-service",
            reaches_module="payment.core",
        )
        ep = TestHelper.create_entry_point(
            method="POST", path="/pay",
            execution_chain=(step,), terminal="database_write",
        )
        change = TestHelper.create_change(
            symbol_id="sym://domain/pay",
            symbol_name="PaymentService",
            symbol_kind="class",
        )
        file_change = TestHelper.create_file_change(changes=(change,))
        rc = TestHelper.create_review_context(
            change=TestHelper.create_change_context(files=(file_change,)),
            execution=TestHelper.create_execution_context(entry_points=(ep,)),
        )
        compiler = LLMContextCompiler()
        result = compiler.compile(rc)

        live = _collect_live_indices(result)
        n = len(result.st.entries)
        dead = set(range(n)) - live
        assert dead == set(), f"Dead indices: {dead}, strings: {[result.st[i] for i in dead]}"

    def test_no_duplicates_after_elimination(self):
        change = TestHelper.create_change(
            symbol_id="sym://app/fn", symbol_name="fn", symbol_kind="function",
        )
        file_change = TestHelper.create_file_change(changes=(change,))
        rc = TestHelper.create_review_context(
            change=TestHelper.create_change_context(files=(file_change,)),
        )
        compiler = LLMContextCompiler()
        result = compiler.compile(rc)
        entries = list(result.st.entries)
        assert len(entries) == len(set(entries))

    def test_empty_string_always_index_zero(self):
        rc = ReviewContext()
        compiler = LLMContextCompiler()
        result = compiler.compile(rc)
        assert result.st[0] == ""

    def test_reaches_strings_retained(self):
        """reaches.service and reaches.module strings appear in table."""
        step = TestHelper.create_execution_step(
            symbol_id="sym://domain/svc",
            symbol_name="SvcClass",
            symbol_kind="class",
            depth=0,
            changed=True,
            reaches_service="my-service",
            reaches_module="my.module",
        )
        ep = TestHelper.create_entry_point(
            method="POST", path="/x", execution_chain=(step,), terminal="db_write",
        )
        change = TestHelper.create_change(
            symbol_id="sym://domain/svc", symbol_name="SvcClass", symbol_kind="class",
        )
        file_change = TestHelper.create_file_change(changes=(change,))
        rc = TestHelper.create_review_context(
            change=TestHelper.create_change_context(files=(file_change,)),
            execution=TestHelper.create_execution_context(entry_points=(ep,)),
        )
        compiler = LLMContextCompiler()
        result = compiler.compile(rc)

        strings = list(result.st.entries)
        assert "my-service" in strings
        assert "my.module" in strings
        assert "db_write" in strings

        # No dead indices
        live = _collect_live_indices(result)
        dead = set(range(len(result.st.entries))) - live
        assert dead == set()


# ---------------------------------------------------------------------------
# Chain Compression (§9)
# ---------------------------------------------------------------------------

class TestChainCompression:

    def test_short_chain_not_compressed(self):
        """Chain ≤ 3 steps returned unchanged."""
        steps = [
            _make_step("sym://a", "A", 0, changed=True),
            _make_step("sym://b", "B", 1),
            _make_step("sym://c", "C", 2),
        ]
        from engine.llm_context.compiler import _compress_chain
        assert _compress_chain(steps, {"sym://a"}) == steps

    def test_long_chain_first_last_retained(self):
        """Chain of 6 helpers: first and last always kept."""
        steps = [_make_step(f"sym://{c}", c, i) for i, c in enumerate("ABCDEF")]
        from engine.llm_context.compiler import _compress_chain
        result = _compress_chain(steps, set())
        assert result[0].symbol.id == "sym://A"
        assert result[-1].symbol.id == "sym://F"
        assert len(result) < 6

    def test_changed_step_preserved(self):
        steps = [
            _make_step("sym://a", "A", 0),
            _make_step("sym://b", "B", 1),
            _make_step("sym://c", "C", 2, changed=True),
            _make_step("sym://d", "D", 3),
            _make_step("sym://e", "E", 4),
            _make_step("sym://f", "F", 5),
        ]
        from engine.llm_context.compiler import _compress_chain
        result = _compress_chain(steps, set())
        assert "sym://c" in [s.symbol.id for s in result]

    def test_boundary_step_preserved(self):
        steps = [
            _make_step("sym://a", "A", 0),
            _make_step("sym://b", "B", 1),
            _make_step("sym://c", "C", 2, reaches_service="ext-service"),
            _make_step("sym://d", "D", 3),
            _make_step("sym://e", "E", 4),
            _make_step("sym://f", "F", 5),
        ]
        from engine.llm_context.compiler import _compress_chain
        result = _compress_chain(steps, set())
        assert "sym://c" in [s.symbol.id for s in result]

    def test_e2e_compressed_in_dag(self):
        """Long chain produces fewer DAG nodes than original steps."""
        steps = tuple([
            _make_step("sym://svc/a", "EntryHandler", 0, changed=True),
            _make_step("sym://svc/b", "HelperB", 1),
            _make_step("sym://svc/c", "HelperC", 2),
            _make_step("sym://svc/d", "HelperD", 3),
            _make_step("sym://svc/e", "HelperE", 4),
            _make_step("sym://svc/f", "Terminal", 5),
        ])
        ep = TestHelper.create_entry_point(
            method="POST", path="/action", execution_chain=steps, max_depth=5,
        )
        change = TestHelper.create_change(
            symbol_id="sym://svc/a", symbol_name="EntryHandler", symbol_kind="function",
        )
        file_change = TestHelper.create_file_change(changes=(change,))
        rc = TestHelper.create_review_context(
            change=TestHelper.create_change_context(files=(file_change,)),
            execution=TestHelper.create_execution_context(entry_points=(ep,)),
        )
        result = LLMContextCompiler().compile(rc)
        assert len(result.eg.nodes) < 6
        assert len(result.eg.nodes) >= 2


# ---------------------------------------------------------------------------
# Discovery-Centred Filtering (§10, §11)
# ---------------------------------------------------------------------------

class TestDiscoveryCentredFiltering:

    def test_only_changed_symbol_in_table(self):
        change = TestHelper.create_change(
            symbol_id="sym://app/fn", symbol_name="fn", symbol_kind="function",
        )
        file_change = TestHelper.create_file_change(path="app.py", changes=(change,))
        rc = TestHelper.create_review_context(
            change=TestHelper.create_change_context(files=(file_change,)),
        )
        result = LLMContextCompiler().compile(rc)
        assert len(result.sym) == 1

    def test_noise_only_ep_excluded(self):
        """EP with only framework noise → excluded after build_review_scope."""
        step_noise = TestHelper.create_execution_step(
            symbol_id="sym://fastapi/Depends",
            symbol_name="Depends",
            symbol_kind="function",
            depth=0,
            changed=False,
        )
        ep = TestHelper.create_entry_point(
            method="GET", path="/noise", execution_chain=(step_noise,),
        )
        rc = TestHelper.create_review_context(
            execution=TestHelper.create_execution_context(entry_points=(ep,)),
        )
        result = LLMContextCompiler().compile(rc)
        assert len(result.eg.nodes) == 0
        assert len(result.epts) == 0

    def test_duplicate_endpoint_deduplicated(self):
        """Two EPs with same (method, path): only one emitted."""
        step = TestHelper.create_execution_step(
            symbol_id="sym://app/handler",
            symbol_name="handler",
            symbol_kind="function",
            depth=0,
            changed=True,
        )
        ep1 = TestHelper.create_entry_point(method="POST", path="/same", execution_chain=(step,))
        ep2 = TestHelper.create_entry_point(method="POST", path="/same", execution_chain=(step,))
        change = TestHelper.create_change(
            symbol_id="sym://app/handler", symbol_name="handler", symbol_kind="function",
        )
        file_change = TestHelper.create_file_change(changes=(change,))
        rc = TestHelper.create_review_context(
            change=TestHelper.create_change_context(files=(file_change,)),
            execution=TestHelper.create_execution_context(entry_points=(ep1, ep2)),
        )
        result = LLMContextCompiler().compile(rc)
        assert len(result.epts) == 1

    def test_all_discoveries_emitted(self):
        d1 = TestHelper.create_discovery(kind="deep_execution", facts={"depth": 3})
        d2 = TestHelper.create_discovery(kind="shared_execution", facts={"count": 2})
        rc = TestHelper.create_review_context(discoveries=(d1, d2))
        result = LLMContextCompiler().compile(rc)
        assert len(result.disc) == 2


# ---------------------------------------------------------------------------
# Validation Invariants (§12)
# ---------------------------------------------------------------------------

class TestValidationInvariants:

    @pytest.fixture
    def multi_ep_rc(self):
        step1 = TestHelper.create_execution_step(
            symbol_id="sym://test/func1", symbol_name="func1",
            kind="function", depth=0, changed=True,
        )
        step2 = TestHelper.create_execution_step(
            symbol_id="sym://test/func2", symbol_name="func2",
            kind="function", depth=1, changed=False,
        )
        step3 = TestHelper.create_execution_step(
            symbol_id="sym://test/func1", symbol_name="func1",
            kind="function", depth=0, changed=True,
        )
        ep1 = TestHelper.create_entry_point(
            method="POST", path="/test1", execution_chain=(step1, step2),
        )
        ep2 = TestHelper.create_entry_point(
            method="GET", path="/test2", execution_chain=(step3,),
        )
        change = TestHelper.create_change(
            symbol_id="sym://test/func1", symbol_name="func1", symbol_kind="function",
        )
        file_change = TestHelper.create_file_change(changes=(change,))
        return TestHelper.create_review_context(
            change=TestHelper.create_change_context(files=(file_change,)),
            execution=TestHelper.create_execution_context(entry_points=(ep1, ep2)),
        )

    def test_no_duplicate_edges(self, multi_ep_rc):
        result = LLMContextCompiler().compile(multi_ep_rc)
        edges = list(result.eg.edges)
        assert len(edges) == len(set(edges))

    def test_no_duplicate_symbol_entries(self, multi_ep_rc):
        result = LLMContextCompiler().compile(multi_ep_rc)
        seen: set[tuple] = set()
        for entry in result.sym:
            assert entry not in seen
            seen.add(entry)

    def test_all_node_sym_indices_valid(self, multi_ep_rc):
        result = LLMContextCompiler().compile(multi_ep_rc)
        for node in result.eg.nodes:
            assert 0 <= node[0] < len(result.sym)

    def test_all_edge_indices_valid(self, multi_ep_rc):
        result = LLMContextCompiler().compile(multi_ep_rc)
        n = len(result.eg.nodes)
        for p, c in result.eg.edges:
            assert 0 <= p < n
            assert 0 <= c < n

    def test_all_ept_ep_indices_valid(self, multi_ep_rc):
        result = LLMContextCompiler().compile(multi_ep_rc)
        for ep_tuple in result.epts:
            assert 0 <= ep_tuple[0] < len(result.ep)

    def test_all_ept_node_indices_valid(self, multi_ep_rc):
        result = LLMContextCompiler().compile(multi_ep_rc)
        n = len(result.eg.nodes)
        for _, chain_nodes, _, _ in result.epts:
            for idx in chain_nodes:
                assert 0 <= idx < n

    def test_all_string_indices_in_bounds(self):
        step = TestHelper.create_execution_step(
            symbol_id="sym://app/fn", symbol_name="fn",
            depth=0, changed=True,
            reaches_service="svc", reaches_module="mod",
        )
        ep = TestHelper.create_entry_point(
            method="POST", path="/p", execution_chain=(step,), terminal="end",
        )
        change = TestHelper.create_change(
            symbol_id="sym://app/fn", symbol_name="fn", symbol_kind="function",
        )
        file_change = TestHelper.create_file_change(changes=(change,))
        rc = TestHelper.create_review_context(
            change=TestHelper.create_change_context(files=(file_change,)),
            execution=TestHelper.create_execution_context(entry_points=(ep,)),
        )
        result = LLMContextCompiler().compile(rc)
        n = len(result.st.entries)

        for path_idx, _ in result.f:
            assert 0 <= path_idx < n
        for _, name_idx, _ in result.sym:
            assert 0 <= name_idx < n
        for _, path_idx in result.ep:
            assert 0 <= path_idx < n
        for _, _, svc_idx, mod_idx in result.eg.nodes:
            assert 0 <= svc_idx < n
            assert 0 <= mod_idx < n
        for _, _, term_idx, _ in result.epts:
            assert 0 <= term_idx < n

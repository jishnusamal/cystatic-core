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


# ---------------------------------------------------------------------------
# LLM Context Token Reduction Tests
# ---------------------------------------------------------------------------

class TestLLMContextTokenReduction:

    def test_symbol_table_deduplication(self):
        """Test that different symbol IDs mapping to the same (file_id, name_idx, kind_id) are deduplicated."""
        # Create two symbol changes in the same file with different IDs but same name and kind
        change1 = TestHelper.create_change(
            symbol_id="sym://app/Module#Checkout",
            symbol_name="Checkout",
            symbol_kind="class",
        )
        change2 = TestHelper.create_change(
            symbol_id="sym://app/CheckoutService#Checkout",
            symbol_name="Checkout",
            symbol_kind="class",
        )
        file_change = TestHelper.create_file_change(
            path="checkout.py",
            changes=(change1, change2),
        )
        rc = TestHelper.create_review_context(
            change=TestHelper.create_change_context(files=(file_change,)),
        )
        compiler = LLMContextCompiler()
        result = compiler.compile(rc)
        
        # Check that only one symbol entry is stored in result.sym
        assert len(result.sym) == 1

    def test_execution_node_merging_across_depths(self):
        """Test that execution nodes with the same behavior and symbol are merged across depths."""
        step1 = TestHelper.create_execution_step(
            symbol_id="sym://app/process",
            symbol_name="process",
            symbol_kind="function",
            depth=1,
            changed=True,
            behavior="behavior://process",
        )
        step2 = TestHelper.create_execution_step(
            symbol_id="sym://app/process",
            symbol_name="process",
            symbol_kind="function",
            depth=3,
            changed=True,
            behavior="behavior://process",
        )
        
        ep1 = TestHelper.create_entry_point(method="POST", path="/endpoint1", execution_chain=(step1,))
        ep2 = TestHelper.create_entry_point(method="POST", path="/endpoint2", execution_chain=(step2,))
        
        change = TestHelper.create_change(
            symbol_id="sym://app/process",
            symbol_name="process",
            symbol_kind="function",
        )
        file_change = TestHelper.create_file_change(changes=(change,))
        rc = TestHelper.create_review_context(
            change=TestHelper.create_change_context(files=(file_change,)),
            execution=TestHelper.create_execution_context(entry_points=(ep1, ep2)),
        )
        
        compiler = LLMContextCompiler()
        result = compiler.compile(rc)
        
        # Check that they merged into a single node in result.eg.nodes
        assert len(result.eg.nodes) == 1
        # The node should store the depth of the first occurrence (minimum depth)
        assert result.eg.nodes[0][1] == 1

    def test_consecutive_step_deduplication(self):
        """Test that consecutive duplicate node indices in chain_node_idxs are deduplicated."""
        step1 = TestHelper.create_execution_step(
            symbol_id="sym://app/helper",
            symbol_name="helper",
            symbol_kind="function",
            depth=1,
            changed=True,
            behavior="behavior://helper",
        )
        step2 = TestHelper.create_execution_step(
            symbol_id="sym://app/helper",
            symbol_name="helper",
            symbol_kind="function",
            depth=2,
            changed=True,
            behavior="behavior://helper",
        )
        
        ep = TestHelper.create_entry_point(method="POST", path="/path", execution_chain=(step1, step2))
        change = TestHelper.create_change(
            symbol_id="sym://app/helper",
            symbol_name="helper",
            symbol_kind="function",
        )
        file_change = TestHelper.create_file_change(changes=(change,))
        rc = TestHelper.create_review_context(
            change=TestHelper.create_change_context(files=(file_change,)),
            execution=TestHelper.create_execution_context(entry_points=(ep,)),
        )
        
        compiler = LLMContextCompiler()
        result = compiler.compile(rc)
        
        # Should merge into 1 node, and the EP chain_nodes list should have length 1 (no consecutive duplicates)
        assert len(result.eg.nodes) == 1
        assert len(result.epts[0][1]) == 1

    def _compile_old(self, rc):
        """Runs the old (baseline) LLMContext compilation logic to measure token baseline."""
        from engine.llm_context.compiler import (
            build_review_scope, _collect_discovery_references, _parse_location,
            _StringBuilder, _enum_id, _resolve_symbol_name_from_uri, _is_noise_string,
            _collect_live_string_indices
        )
        from engine.llm_context.model import LLMContext, StringTable, ExecutionGraph, ENUM_METHOD
        
        compiler = LLMContextCompiler()
        pruned_context = build_review_scope(rc, settings=compiler._settings)
        
        changed_symbol_ids = set()
        changed_file_paths = set()
        if pruned_context.change and pruned_context.change.files:
            for f in pruned_context.change.files:
                changed_file_paths.add(f.path)
                for c in f.changes:
                    if c.symbol and c.symbol.id:
                        changed_symbol_ids.add(c.symbol.id)

        disc_symbol_ids, disc_behavior_ids, disc_endpoint_keys = _collect_discovery_references(
            pruned_context.discoveries
        )

        retained_eps = compiler._filter_entry_points(
            pruned_context.execution,
            changed_symbol_ids,
            disc_symbol_ids,
            disc_behavior_ids,
            disc_endpoint_keys,
        )

        # Baseline: collect symbol IDs and file paths from ALL retained entry points
        chain_symbol_ids = set()
        for ep, compressed_steps in retained_eps:
            for step in compressed_steps:
                if step.symbol and step.symbol.id:
                    chain_symbol_ids.add(step.symbol.id)

        sb = _StringBuilder()

        chain_file_paths = set()
        for ep, compressed_steps in retained_eps:
            for step in compressed_steps:
                if step.symbol and step.symbol.location:
                    fp, _, _ = _parse_location(step.symbol.location)
                    if fp:
                        chain_file_paths.add(fp)

        retained_file_paths = changed_file_paths | chain_file_paths

        file_table = compiler._build_file_table_filtered(
            pruned_context.change,
            retained_file_paths,
            sb,
        )

        file_idx_map = {}
        for i, entry in enumerate(file_table):
            file_idx_map[sb.get_string(entry[0])] = i

        # Baseline symbol table: keyed by sym.id, no deduplication, iterates over pruned_context.execution
        symbol_table = []
        seen = {}
        symbols_per_file = {}
        for f in pruned_context.change.files:
            for c in f.changes:
                sym = c.symbol
                if sym.id not in seen:
                    file_path, _, _ = _parse_location(sym.location)
                    file_id = file_idx_map.get(file_path, 0)
                    derivable_name = _resolve_symbol_name_from_uri(sym.id)
                    name_idx = 0 if sym.name == derivable_name else sb.add(sym.name)
                    sym_entry = (file_id, name_idx, _enum_id("kind", sym.kind))
                    seen[sym.id] = len(symbol_table)
                    symbol_table.append(sym_entry)
                    symbols_per_file[file_id] = symbols_per_file.get(file_id, 0) + 1

        all_referenced = chain_symbol_ids | disc_symbol_ids
        if pruned_context.execution and pruned_context.execution.entry_points:
            for ep in pruned_context.execution.entry_points:
                for step in ep.execution_chain:
                    sym = step.symbol
                    if sym and sym.id and sym.id not in seen:
                        if sym.id not in all_referenced:
                            continue
                        file_path, _, _ = _parse_location(sym.location)
                        file_id = file_idx_map.get(file_path, 0)
                        limit = compiler._settings.LLM_CONTEXT_MAX_SYMBOLS_PER_FILE
                        if symbols_per_file.get(file_id, 0) >= limit:
                            continue
                        derivable_name = _resolve_symbol_name_from_uri(sym.id)
                        if sym.name == derivable_name or _is_noise_string(sym.name):
                            name_idx = 0
                        else:
                            name_idx = sb.add(sym.name)
                        sym_entry = (file_id, name_idx, _enum_id("kind", sym.kind))
                        seen[sym.id] = len(symbol_table)
                        symbol_table.append(sym_entry)
                        symbols_per_file[file_id] = symbols_per_file.get(file_id, 0) + 1

        # Baseline endpoint table
        endpoint_table = []
        seen_eps = {}
        for ep, _ in retained_eps:
            key = (ep.method, ep.path)
            if key not in seen_eps:
                entry = (_enum_id("method", ep.method), sb.add(ep.path))
                seen_eps[key] = len(endpoint_table)
                endpoint_table.append(entry)

        endpoint_idx_map = {}
        for i, ep_entry in enumerate(endpoint_table):
            method_id, path_idx = ep_entry
            method_str = ENUM_METHOD.get(method_id, "")
            path_str = sb.get_string(path_idx)
            endpoint_idx_map[(method_str, path_str)] = i

        change_summary = compiler._build_change_summary(pruned_context.change.summary, sb)
        
        # Build changes for change_files remapping
        change_files = []
        for file_entry in file_table:
            path = sb.get_string(file_entry[0])
            for f in pruned_context.change.files:
                if f.path == path:
                    changed_sym_idxs = []
                    for c in f.changes:
                        sym_idx = seen.get(c.symbol.id, -1)
                        if sym_idx >= 0 and sym_idx not in changed_sym_idxs:
                            changed_sym_idxs.append(sym_idx)
                    file_idx = next(i for i, entry in enumerate(file_table) if sb.get_string(entry[0]) == path)
                    change_files.append((file_idx, tuple(changed_sym_idxs)))

        # Baseline execution building: node_key has depth, no node merging, no chain deduplication
        node_map = {}
        nodes = []
        edges = []
        entry_point_data = []
        for ep, compressed_steps in retained_eps:
            key = (ep.method, ep.path)
            if key not in endpoint_idx_map:
                continue
            chain_node_idxs = []
            prev_node_idx = None
            for step in compressed_steps:
                node_key = (step.behavior, step.symbol.id, step.depth)
                if node_key not in node_map:
                    node_idx = len(nodes)
                    node_map[node_key] = node_idx
                    sym_idx = seen.get(step.symbol.id, 0)
                    reaches_svc_idx = sb.add(step.reaches.service) if step.reaches.service else 0
                    reaches_mod_idx = sb.add(step.reaches.module) if step.reaches.module else 0
                    node = (sym_idx, step.depth, reaches_svc_idx, reaches_mod_idx)
                    nodes.append(node)
                else:
                    node_idx = node_map[node_key]
                chain_node_idxs.append(node_idx)
                if prev_node_idx is not None:
                    edge = (prev_node_idx, node_idx)
                    if edge not in edges:
                        edges.append(edge)
                prev_node_idx = node_idx
            endpoint_idx = endpoint_idx_map[key]
            terminal_idx = sb.add(ep.terminal) if ep.terminal else 0
            ep_tuple = (endpoint_idx, tuple(chain_node_idxs), terminal_idx, ep.max_depth)
            entry_point_data.append(ep_tuple)

        discoveries = compiler._build_discoveries(pruned_context.discoveries, sb)

        live_indices = _collect_live_string_indices(
            file_table,
            symbol_table,
            endpoint_table,
            change_files,
            nodes,
            entry_point_data,
            sb,
        )

        old_to_new = {0: 0}
        new_strings = [""]
        for old_idx in sorted(live_indices):
            if old_idx == 0:
                continue
            if old_idx < len(sb.strings):
                new_idx = len(new_strings)
                new_strings.append(sb.strings[old_idx])
                old_to_new[old_idx] = new_idx

        remapped_file_table = [(old_to_new.get(path_idx, 0), ct_id) for path_idx, ct_id in file_table]
        remapped_symbol_table = [(file_id, old_to_new.get(name_idx, 0), kind_id) for file_id, name_idx, kind_id in symbol_table]
        remapped_endpoint_table = [(method_id, old_to_new.get(path_idx, 0)) for method_id, path_idx in endpoint_table]
        remapped_nodes = tuple((sym_idx, depth, old_to_new.get(svc_idx, 0), old_to_new.get(mod_idx, 0)) for sym_idx, depth, svc_idx, mod_idx in nodes)
        remapped_epts = tuple((ep_idx, chain_nodes, old_to_new.get(term_idx, 0), max_depth) for ep_idx, chain_nodes, term_idx, max_depth in entry_point_data)
        compact_st = StringTable(entries=tuple(new_strings))

        return LLMContext(
            st=compact_st,
            f=tuple(remapped_file_table),
            sym=tuple(remapped_symbol_table),
            ep=tuple(remapped_endpoint_table),
            cs=change_summary,
            cf=tuple(change_files),
            eg=ExecutionGraph(nodes=remapped_nodes, edges=tuple(edges)),
            epts=remapped_epts,
            disc=tuple(discoveries),
        )

    def test_large_pr_token_reduction_measurement(self):
        """Build a mock large ReviewContext simulating the large PR stats, and measure token count."""
        entry_points = []
        changes = []
        
        # Generate 150 entry points with varying steps to simulate a large PR context
        # (This will be pruned down to 50 in selected_eps)
        for i in range(150):
            steps = []
            # Each chain has 10 steps
            for d in range(10):
                # Multiple symbol IDs point to the same symbol to simulate duplicates
                sym_id = f"sym://file_{i % 10}/func_{d % 3}#func_{d % 3}"
                step = TestHelper.create_execution_step(
                    symbol_id=sym_id,
                    symbol_name=f"func_{d % 3}",
                    symbol_kind="function",
                    depth=d,
                    changed=True,
                    behavior=f"behavior://file_{i % 10}/func_{d % 3}",
                )
                steps.append(step)
                
                # Add changes
                if i < 20 and d % 2 == 0:
                    changes.append(TestHelper.create_change(
                        symbol_id=sym_id,
                        symbol_name=f"func_{d % 3}",
                        symbol_kind="function",
                    ))
            
            ep = TestHelper.create_entry_point(
                method="POST",
                path=f"/route_{i}",
                execution_chain=tuple(steps),
                terminal="return",
                max_depth=9,
            )
            entry_points.append(ep)
            
        file_change = TestHelper.create_file_change(
            path="large_service.py",
            changes=tuple(changes),
        )
        
        rc = TestHelper.create_review_context(
            change=TestHelper.create_change_context(
                classification="modification",
                scope="multi_file",
                file_count=10,
                symbol_count=len(changes),
                files=(file_change,),
            ),
            execution=TestHelper.create_execution_context(entry_points=tuple(entry_points)),
        )
        
        from engine.pipeline.pipeline import PipelineContext, Pipeline
        pipeline = Pipeline()
        
        context_old = PipelineContext(run_context=None, repository="test/repo")
        context_old.review_context = rc
        
        # Compile old
        context_old.llm_context = self._compile_old(rc)
        serialized_old = pipeline.serialize_llm_context(context_old)
        token_counts_old = pipeline.calculate_llm_context_tokens(serialized_old)
        
        context_new = PipelineContext(run_context=None, repository="test/repo")
        context_new.review_context = rc
        
        # Compile new
        compiler = LLMContextCompiler()
        context_new.llm_context = compiler.compile(rc)
        serialized_new = pipeline.serialize_llm_context(context_new)
        token_counts_new = pipeline.calculate_llm_context_tokens(serialized_new)
        
        assert token_counts_old is not None
        assert token_counts_new is not None
        
        old_total = token_counts_old.get('total', 1)
        new_total = token_counts_new.get('total', 1)
        reduction = old_total - new_total
        percent = (reduction / old_total) * 100
        
        print("\n=== COMPARISON OF TOKEN COUNTS ===")
        print("BEFORE (Baseline)")
        print(f"sym:   {token_counts_old.get('sym')}")
        print(f"epts:  {token_counts_old.get('epts')}")
        print(f"st:    {token_counts_old.get('st')}")
        print(f"total: {old_total}")
        print("--------------------")
        print("AFTER (Optimized)")
        print(f"sym:   {token_counts_new.get('sym')}")
        print(f"epts:  {token_counts_new.get('epts')}")
        print(f"st:    {token_counts_new.get('st')}")
        print(f"total: {new_total}")
        print("--------------------")
        print("REDUCTION")
        print(f"Absolute: {reduction} tokens")
        print(f"Percentage: {percent:.2f}%")
        print("==================================")
        
        assert percent > 50.0

    def test_generate_llm_comment_with_compressed_context(self):
        """Test that generate_llm_comment accepts and uses llm_context_compressed."""
        change = TestHelper.create_change(
            symbol_id="sym://app/fn", symbol_name="fn", symbol_kind="function",
        )
        file_change = TestHelper.create_file_change(path="app.py", changes=(change,))
        rc = TestHelper.create_review_context(
            change=TestHelper.create_change_context(files=(file_change,)),
        )
        
        from engine.pipeline.pipeline import PipelineContext, Pipeline
        pipeline = Pipeline()
        context = PipelineContext(run_context=None, repository="test/repo")
        context.review_context = rc
        
        compiler = LLMContextCompiler()
        context.llm_context = compiler.compile(rc)
        
        # Create a mock compressed context
        mock_compressed = {
            "st": ["", "custom_compressed_string"],
            "sym": [[0, 1, 2]]
        }
        
        # Mock the OpenAI client so it doesn't make a real network call
        class MockChoices:
            def __init__(self):
                class MockMessage:
                    content = "Mock briefing content"
                self.message = MockMessage()

        class MockResponse:
            def __init__(self):
                self.choices = [MockChoices()]
                self.model = "mock-model"

        class MockChatCompletions:
            def create(self, *args, **kwargs):
                messages = kwargs.get("messages", [])
                assert len(messages) == 2
                user_msg = messages[1]["content"]
                assert "custom_compressed_string" in user_msg
                return MockResponse()

        class MockChat:
            def __init__(self):
                self.completions = MockChatCompletions()

        class MockOpenAI:
            def __init__(self, *args, **kwargs):
                self.chat = MockChat()

            def __enter__(self):
                return self
            
            def __exit__(self, exc_type, exc_val, exc_tb):
                pass
                
        import sys
        import core.config
        
        class MockSettings:
            AI_API_KEY = "mock-key"
            AI_API_BASE_URL = "http://mock-url"
            AI_MODEL = "mock-model"
            
        orig_get_settings = core.config.get_settings
        core.config.get_settings = lambda: MockSettings()
        
        orig_openai = sys.modules.get('openai')
        
        class FakeOpenAIModule:
            OpenAI = MockOpenAI
            
        sys.modules['openai'] = FakeOpenAIModule

        try:
            res = pipeline.generate_llm_comment(
                context,
                repository="test/repo",
                pr_number="123",
                language="python",
                llm_context_compressed=mock_compressed,
            )
            assert res["generated"] is True
            assert res["comment"] == "Mock briefing content"
        finally:
            core.config.get_settings = orig_get_settings
            if orig_openai is not None:
                sys.modules['openai'] = orig_openai
            else:
                del sys.modules['openai']

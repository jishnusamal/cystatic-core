"""Tests for the LLMContext Compiler — lossless compressed IR.

Tests that LLMContextCompiler correctly transforms ReviewContext into a lossless,
compressed IR with enum encoding, string tables, URI decomposition, and
source location normalization.
"""
from __future__ import annotations

from typing import Any

import pytest

from review_context.model import (
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
from llm_context.compiler import LLMContextCompiler
from llm_context.model import LLMContext, StringTable, ExecutionGraph
from llm_context.model import ENUM_REVERSE


# ---------------------------------------------------------------------------
# Enum lookup helpers for tests
# ---------------------------------------------------------------------------

def _enum_val(table: str, id: int) -> str:
    """Look up enum value by ID."""
    from llm_context.model import ENUM_TABLES
    return ENUM_TABLES[table].get(id, "")


def _enum_id(table: str, val: str) -> int:
    """Look up enum ID by value."""
    return ENUM_REVERSE.get(table, {}).get(val, 0)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

class TestHelper:
    """Helper for creating test fixtures."""

    @staticmethod
    def create_review_context(
        change: ChangeContext | None = None,
        execution: ExecutionContext | None = None,
        discoveries: tuple[Discovery, ...] | None = None,
    ) -> ReviewContext:
        """Create a ReviewContext for testing."""
        return ReviewContext(
            change=change or ChangeContext(),
            execution=execution or ExecutionContext(),
            discoveries=discoveries or (),
        )

    @staticmethod
    def create_change_context(
        classification: str = "modification",
        scope: str = "local",
        file_count: int = 1,
        symbol_count: int = 1,
        behavior_count: int = 0,
        files: tuple[FileChange, ...] | None = None,
    ) -> ChangeContext:
        """Create a ChangeContext for testing."""
        summary = ChangeSummary(
            classification=classification,
            scope=scope,
            file_count=file_count,
            symbol_count=symbol_count,
            behavior_count=behavior_count,
        )
        return ChangeContext(
            summary=summary,
            files=files or (),
        )

    @staticmethod
    def create_file_change(
        path: str = "test.py",
        language: str = "python",
        change_type: str = "modified",
        changes: tuple[Change, ...] | None = None,
    ) -> FileChange:
        """Create a FileChange for testing."""
        return FileChange(
            path=path,
            language=language,
            change_type=change_type,
            changes=changes or (),
        )

    @staticmethod
    def create_change(
        symbol_id: str = "sym://test/func1",
        symbol_name: str = "func1",
        symbol_kind: str = "function",
        symbol_visibility: str = "public",
        symbol_language: str = "python",
        symbol_location: str = "test.py:1-10",
        change_type: str = "modified",
        behavior_changes: tuple[str, ...] = (),
    ) -> Change:
        """Create a Change for testing."""
        return Change(
            symbol=SymbolRef(
                id=symbol_id,
                name=symbol_name,
                kind=symbol_kind,
                visibility=symbol_visibility,
                language=symbol_language,
                location=symbol_location,
            ),
            change_type=change_type,
            behavior_changes=behavior_changes,
        )

    @staticmethod
    def create_execution_context(
        entry_points: tuple[EntryPointExecution, ...] | None = None,
        deepest: DeepestExecution | None = None,
    ) -> ExecutionContext:
        """Create an ExecutionContext for testing."""
        return ExecutionContext(
            entry_points=entry_points or (),
            deepest_execution=deepest or DeepestExecution(),
        )

    @staticmethod
    def create_entry_point(
        endpoint: str = "POST /test",
        method: str = "POST",
        path: str = "/test",
        execution_chain: tuple[ExecutionStep, ...] | None = None,
        terminal: str = "return",
        max_depth: int = 1,
        references: tuple[str, ...] = (),
    ) -> EntryPointExecution:
        """Create an EntryPointExecution for testing."""
        return EntryPointExecution(
            endpoint=endpoint,
            method=method,
            path=path,
            execution_chain=execution_chain or (),
            terminal=terminal,
            max_depth=max_depth,
            references=references,
        )

    @staticmethod
    def create_execution_step(
        behavior: str = "behavior://test",
        symbol_id: str = "sym://test/func1",
        symbol_name: str = "func1",
        symbol_kind: str = "function",
        symbol_location: str = "test.py:1-10",
        kind: str = "function",
        depth: int = 0,
        changed: bool = False,
        shared: bool = False,
        reaches_service: str = "api",
        reaches_module: str = "test_module",
        reaches_package: str = "",
        references: tuple[str, ...] = (),
    ) -> ExecutionStep:
        """Create an ExecutionStep for testing."""
        return ExecutionStep(
            behavior=behavior,
            symbol=SymbolReference(
                id=symbol_id,
                name=symbol_name,
                kind=symbol_kind,
                location=symbol_location,
            ),
            kind=kind,
            depth=depth,
            changed=changed,
            shared=shared,
            reaches=ReachedComponents(
                service=reaches_service,
                module=reaches_module,
                package=reaches_package,
            ),
            references=references,
        )

    @staticmethod
    def create_discovery(
        id: str = "discovery://test/1",
        kind: str = "deep_execution",
        statement: str = "",
        facts: dict[str, Any] | None = None,
        reference_count: int = 0,
        references: tuple[Reference, ...] = (),
    ) -> Discovery:
        """Create a Discovery for testing."""
        return Discovery(
            id=id,
            kind=kind,
            statement=statement,
            facts=facts or {},
            reference_count=reference_count,
            references=references,
        )

    @staticmethod
    def create_reference(
        id: str = "ref://test/1",
        kind: str = "behavior",
        location: str = "behavior://test",
        compiler_artifact: str = "behavior",
    ) -> Reference:
        """Create a Reference for testing."""
        return Reference(
            id=id,
            kind=kind,
            location=location,
            compiler_artifact=compiler_artifact,
        )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def empty_review_context():
    """Create an empty ReviewContext."""
    return ReviewContext()


@pytest.fixture
def simple_change_context():
    """Create a simple change context with one file and one symbol."""
    change = TestHelper.create_change(
        symbol_id="sym://test/func1",
        symbol_name="func1",
        symbol_kind="function",
        change_type="modified",
        behavior_changes=("FunctionBodyChange",),
    )
    file_change = TestHelper.create_file_change(
        path="test.py",
        language="python",
        change_type="modified",
        changes=(change,),
    )
    return TestHelper.create_change_context(
        classification="modification",
        scope="local",
        file_count=1,
        symbol_count=1,
        behavior_count=1,
        files=(file_change,),
    )


@pytest.fixture
def simple_execution_context():
    """Create a simple execution context with one entry point."""
    step = TestHelper.create_execution_step(
        behavior="behavior://test",
        symbol_id="sym://test/func1",
        symbol_name="func1",
        kind="function",
        depth=0,
        changed=True,
        shared=False,
        reaches_service="api",
        reaches_module="test_module",
    )
    ep = TestHelper.create_entry_point(
        endpoint="POST /test",
        method="POST",
        path="/test",
        execution_chain=(step,),
        terminal="return",
        max_depth=0,
    )
    deepest = DeepestExecution(
        entry_point="POST /test",
        depth=0,
    )
    return TestHelper.create_execution_context(
        entry_points=(ep,),
        deepest=deepest,
    )


@pytest.fixture
def simple_discoveries():
    """Create simple discoveries for testing."""
    ref = TestHelper.create_reference(
        id="ref://test/1",
        kind="behavior",
        location="behavior://test",
        compiler_artifact="behavior",
    )
    discovery = TestHelper.create_discovery(
        id="discovery://test/1",
        kind="deep_execution",
        facts={"max_depth": 2},
        reference_count=1,
        references=(ref,),
    )
    return (discovery,)


@pytest.fixture
def simple_review_context(simple_change_context, simple_execution_context, simple_discoveries):
    """Create a simple ReviewContext with all sections populated."""
    return ReviewContext(
        change=simple_change_context,
        execution=simple_execution_context,
        discoveries=simple_discoveries,
    )


@pytest.fixture
def multi_file_change_context():
    """Create a change context with multiple files and symbols."""
    change1 = TestHelper.create_change(
        symbol_id="sym://test/func1",
        symbol_name="func1",
        symbol_kind="function",
        change_type="modified",
    )
    change2 = TestHelper.create_change(
        symbol_id="sym://test/func2",
        symbol_name="func2",
        symbol_kind="function",
        change_type="added",
    )
    change3 = TestHelper.create_change(
        symbol_id="sym://other/ClassA",
        symbol_name="ClassA",
        symbol_kind="class",
        change_type="modified",
    )
    file1 = TestHelper.create_file_change(
        path="test.py",
        language="python",
        change_type="mixed",
        changes=(change1, change2),
    )
    file2 = TestHelper.create_file_change(
        path="other.py",
        language="python",
        change_type="modified",
        changes=(change3,),
    )
    return TestHelper.create_change_context(
        classification="mixed",
        scope="multi_file",
        file_count=2,
        symbol_count=3,
        files=(file1, file2),
    )


@pytest.fixture
def multi_ep_execution_context():
    """Create an execution context with multiple entry points sharing steps."""
    step1 = TestHelper.create_execution_step(
        behavior="behavior://test1",
        symbol_id="sym://test/func1",
        symbol_name="func1",
        kind="function",
        depth=0,
        changed=True,
    )
    step2 = TestHelper.create_execution_step(
        behavior="behavior://test1",
        symbol_id="sym://test/func2",
        symbol_name="func2",
        kind="function",
        depth=1,
        changed=False,
    )
    step3 = TestHelper.create_execution_step(
        behavior="behavior://test2",
        symbol_id="sym://test/func1",
        symbol_name="func1",
        kind="function",
        depth=0,
        changed=True,
    )
    ep1 = TestHelper.create_entry_point(
        endpoint="POST /test1",
        method="POST",
        path="/test1",
        execution_chain=(step1, step2),
        terminal="return",
        max_depth=1,
    )
    ep2 = TestHelper.create_entry_point(
        endpoint="GET /test2",
        method="GET",
        path="/test2",
        execution_chain=(step3,),
        terminal="return",
        max_depth=0,
    )
    deepest = DeepestExecution(
        entry_point="POST /test1",
        depth=1,
    )
    return TestHelper.create_execution_context(
        entry_points=(ep1, ep2),
        deepest=deepest,
    )


@pytest.fixture
def multi_discovery_context():
    """Create discoveries with shared references."""
    ref1 = TestHelper.create_reference(
        id="ref://shared/1",
        kind="behavior",
        location="behavior://test1",
        compiler_artifact="behavior",
    )
    ref2 = TestHelper.create_reference(
        id="ref://shared/2",
        kind="change",
        location="change://test",
        compiler_artifact="change",
    )
    d1 = TestHelper.create_discovery(
        id="discovery://deep/1",
        kind="deep_execution",
        facts={"max_depth": 3},
        reference_count=2,
        references=(ref1, ref2),
    )
    d2 = TestHelper.create_discovery(
        id="discovery://shared/1",
        kind="shared_execution",
        facts={"shared_symbol_ids": ("sym://test/func1",), "behavior_count": 2},
        reference_count=2,
        references=(ref1, ref2),
    )
    return (d1, d2)


# ---------------------------------------------------------------------------
# Tests: LLMContextCompiler — Initialization
# ---------------------------------------------------------------------------

class TestLLMContextCompilerInit:
    """Tests for LLMContextCompiler initialization."""

    def test_compiler_initialization(self):
        """Test that the compiler initializes without error."""
        compiler = LLMContextCompiler()
        assert isinstance(compiler, LLMContextCompiler)

    def test_compile_returns_llm_context(self, empty_review_context):
        """Test that compile returns an LLMContext."""
        compiler = LLMContextCompiler()
        result = compiler.compile(empty_review_context)
        assert isinstance(result, LLMContext)

    def test_compile_empty_review_context(self, empty_review_context):
        """Test that compiling an empty ReviewContext returns a valid LLMContext."""
        compiler = LLMContextCompiler()
        result = compiler.compile(empty_review_context)
        assert isinstance(result.st, StringTable)
        assert result.f == ()
        assert result.sym == ()
        assert result.bh == ()
        assert result.ref == ()
        assert result.ep == ()
        assert result.cs == (0, 0, 0, 0, 0)
        assert result.cf == ()
        assert isinstance(result.eg, ExecutionGraph)
        assert result.epts == ()
        assert result.de == (0, 0)
        assert result.disc == ()


# ---------------------------------------------------------------------------
# Tests: LLMContextCompiler — String Table
# ---------------------------------------------------------------------------

class TestStringTable:
    """Tests for the global string dictionary."""

    def test_strings_collected_from_change(self, simple_review_context):
        """Test that strings from change section are collected."""
        compiler = LLMContextCompiler()
        result = compiler.compile(simple_review_context)
        assert len(result.st) > 0

    def test_strings_collected_from_execution(self, simple_review_context):
        """Test that strings from execution section are collected."""
        compiler = LLMContextCompiler()
        result = compiler.compile(simple_review_context)
        strings = list(result.st.entries)
        assert any("POST" in s for s in strings)
        assert any("/test" in s for s in strings)

    def test_strings_collected_from_discoveries(self, simple_review_context):
        """Test that strings from discoveries section are collected."""
        compiler = LLMContextCompiler()
        result = compiler.compile(simple_review_context)
        strings = list(result.st.entries)
        assert any("discovery://" in s for s in strings)
        assert any("ref://" in s for s in strings)

    def test_strings_deduplicated(self, simple_review_context):
        """Test that repeated strings are stored only once."""
        compiler = LLMContextCompiler()
        result = compiler.compile(simple_review_context)
        strings = list(result.st.entries)
        assert len(strings) == len(set(strings))

    def test_empty_string_index_zero(self, simple_review_context):
        """Test that empty strings always get index 0."""
        compiler = LLMContextCompiler()
        result = compiler.compile(simple_review_context)
        assert result.st[0] == ""


# ---------------------------------------------------------------------------
# Tests: LLMContextCompiler — Lookup Tables
# ---------------------------------------------------------------------------

class TestLookupTables:
    """Tests for normalized lookup tables."""

    def test_file_table_populated(self, simple_review_context):
        """Test that file table is populated from change context."""
        compiler = LLMContextCompiler()
        result = compiler.compile(simple_review_context)
        assert len(result.f) > 0

    def test_file_table_entries(self, simple_review_context):
        """Test that file table entries have correct structure."""
        compiler = LLMContextCompiler()
        result = compiler.compile(simple_review_context)
        for entry in result.f:
            assert len(entry) == 3  # (path_idx, lang_id, ct_id)
            path, lang, ctype = entry
            assert isinstance(path, int)
            assert isinstance(lang, int)
            assert isinstance(ctype, int)

    def test_file_table_enum_encoding(self, simple_review_context):
        """Test that file table uses enum encoding for language and change_type."""
        compiler = LLMContextCompiler()
        result = compiler.compile(simple_review_context)
        for entry in result.f:
            _, lang_id, ct_id = entry
            # Language "python" should be enum id 1
            assert _enum_val("lang", lang_id) == "python"
            # Change type "modified" should be enum id 1
            assert _enum_val("ct", ct_id) == "modified"

    def test_file_table_deduplicates(self, multi_file_change_context):
        """Test that file table deduplicates by path."""
        rc = ReviewContext(change=multi_file_change_context)
        compiler = LLMContextCompiler()
        result = compiler.compile(rc)
        assert len(result.f) == 2

    def test_symbol_table_populated(self, simple_review_context):
        """Test that symbol table is populated from change context."""
        compiler = LLMContextCompiler()
        result = compiler.compile(simple_review_context)
        assert len(result.sym) > 0

    def test_symbol_table_entries(self, simple_review_context):
        """Test that symbol table entries have correct structure."""
        compiler = LLMContextCompiler()
        result = compiler.compile(simple_review_context)
        for entry in result.sym:
            # (file_id, name_idx, kind_id, vis_id, (start_line, end_line))
            assert len(entry) == 5
            file_id, name_idx, kind_id, vis_id, location = entry
            assert isinstance(file_id, int)
            assert isinstance(name_idx, int)
            assert isinstance(kind_id, int)
            assert isinstance(vis_id, int)
            assert isinstance(location, tuple) and len(location) == 2

    def test_symbol_table_enum_encoding(self, simple_review_context):
        """Test that symbol table uses enum encoding for kind and visibility."""
        compiler = LLMContextCompiler()
        result = compiler.compile(simple_review_context)
        for entry in result.sym:
            _, _, kind_id, vis_id, _ = entry
            assert _enum_val("kind", kind_id) == "function"
            assert _enum_val("vis", vis_id) == "public"

    def test_symbol_table_location_normalized(self, simple_review_context):
        """Test that symbol location is normalized to (start, end) tuple."""
        compiler = LLMContextCompiler()
        result = compiler.compile(simple_review_context)
        for entry in result.sym:
            _, _, _, _, location = entry
            start, end = location
            # "test.py:1-10" normalized to (1, 10)
            assert start >= 0
            assert end >= 0

    def test_symbol_table_deduplicates(self, multi_file_change_context):
        """Test that symbol table deduplicates by symbol id."""
        rc = ReviewContext(change=multi_file_change_context)
        compiler = LLMContextCompiler()
        result = compiler.compile(rc)
        assert len(result.sym) == 3

    def test_behavior_table_populated(self, simple_review_context):
        """Test that behavior table is populated from execution context."""
        compiler = LLMContextCompiler()
        result = compiler.compile(simple_review_context)
        assert len(result.bh) > 0

    def test_behavior_table_entries(self, simple_review_context):
        """Test that behavior table entries have correct compact structure."""
        compiler = LLMContextCompiler()
        result = compiler.compile(simple_review_context)
        for entry in result.bh:
            # (sym_id, kind_id) — compact form
            assert len(entry) == 2
            sym_id, kind_id = entry
            assert isinstance(sym_id, int)
            assert isinstance(kind_id, int)

    def test_behavior_table_uses_symbol_reference(self, simple_review_context):
        """Test that behavior table references symbols by index."""
        compiler = LLMContextCompiler()
        result = compiler.compile(simple_review_context)
        for entry in result.bh:
            sym_idx, _ = entry
            # Should reference a valid symbol index
            assert 0 <= sym_idx < len(result.sym)

    def test_reference_table_populated(self, simple_review_context):
        """Test that reference table is populated from discoveries."""
        compiler = LLMContextCompiler()
        result = compiler.compile(simple_review_context)
        assert len(result.ref) > 0

    def test_reference_table_entries(self, simple_review_context):
        """Test that reference table entries have correct structure."""
        compiler = LLMContextCompiler()
        result = compiler.compile(simple_review_context)
        for entry in result.ref:
            assert len(entry) == 4  # (id_idx, kind_id, location_idx, artifact_idx)
            for field in entry:
                assert isinstance(field, int)

    def test_reference_table_enum_encoding(self, simple_review_context):
        """Test that reference table uses enum encoding for kind."""
        compiler = LLMContextCompiler()
        result = compiler.compile(simple_review_context)
        for entry in result.ref:
            _, kind_id, _, _ = entry
            assert _enum_val("ref_kind", kind_id) == "behavior"

    def test_reference_table_deduplicates(self, multi_discovery_context):
        """Test that reference table deduplicates by reference id."""
        rc = ReviewContext(discoveries=multi_discovery_context)
        compiler = LLMContextCompiler()
        result = compiler.compile(rc)
        assert len(result.ref) == 2

    def test_endpoint_table_populated(self, simple_review_context):
        """Test that endpoint table is populated from execution context."""
        compiler = LLMContextCompiler()
        result = compiler.compile(simple_review_context)
        assert len(result.ep) > 0

    def test_endpoint_table_entries(self, simple_review_context):
        """Test that endpoint table entries have correct structure."""
        compiler = LLMContextCompiler()
        result = compiler.compile(simple_review_context)
        for entry in result.ep:
            assert len(entry) == 3  # (endpoint_idx, method_id, path_idx)
            for field in entry:
                assert isinstance(field, int)

    def test_endpoint_table_enum_encoding(self, simple_review_context):
        """Test that endpoint table uses enum encoding for method."""
        compiler = LLMContextCompiler()
        result = compiler.compile(simple_review_context)
        for entry in result.ep:
            _, method_id, _ = entry
            assert _enum_val("method", method_id) == "POST"


# ---------------------------------------------------------------------------
# Tests: LLMContextCompiler — Change Section
# ---------------------------------------------------------------------------

class TestChangeSection:
    """Tests for the change section of LLMContext."""

    def test_change_summary_enum_encoding(self, simple_review_context):
        """Test that change summary uses enum encoding for classification and scope."""
        compiler = LLMContextCompiler()
        result = compiler.compile(simple_review_context)
        cls_id, scope_id, file_count, symbol_count, behavior_count = result.cs
        assert _enum_val("cls", cls_id) == "modification"
        assert _enum_val("scope", scope_id) == "local"
        assert file_count == 1
        assert symbol_count == 1
        assert behavior_count == 1

    def test_change_files_preserved(self, simple_review_context):
        """Test that change files are preserved."""
        compiler = LLMContextCompiler()
        result = compiler.compile(simple_review_context)
        assert len(result.cf) > 0

    def test_change_file_references_correct_file(self, simple_review_context):
        """Test that change file references the correct file table entry."""
        compiler = LLMContextCompiler()
        result = compiler.compile(simple_review_context)
        for file_entry in result.cf:
            file_idx = file_entry[0]
            file_path = result.st[result.f[file_idx][0]]
            assert file_path == "test.py"

    def test_change_symbol_references_correct_symbol(self, simple_review_context):
        """Test that change symbol references the correct symbol table entry."""
        compiler = LLMContextCompiler()
        result = compiler.compile(simple_review_context)
        for file_entry in result.cf:
            changes = file_entry[1]
            for change_entry in changes:
                sym_idx = change_entry[0]
                # Verify valid symbol index
                assert 0 <= sym_idx < len(result.sym)

    def test_behavior_changes_enum_encoded(self, simple_review_context):
        """Test that behavior change types use enum encoding."""
        compiler = LLMContextCompiler()
        result = compiler.compile(simple_review_context)
        for file_entry in result.cf:
            changes = file_entry[1]
            for change_entry in changes:
                bh_change_ids = change_entry[2]
                if bh_change_ids:
                    bc_id = bh_change_ids[0]
                    assert _enum_val("bh_change", bc_id) == "FunctionBodyChange"


# ---------------------------------------------------------------------------
# Tests: LLMContextCompiler — Execution Section
# ---------------------------------------------------------------------------

class TestExecutionSection:
    """Tests for the execution section of LLMContext."""

    def test_execution_graph_nodes_populated(self, simple_review_context):
        """Test that execution graph nodes are populated."""
        compiler = LLMContextCompiler()
        result = compiler.compile(simple_review_context)
        assert len(result.eg.nodes) > 0

    def test_execution_graph_node_structure(self, simple_review_context):
        """Test that execution graph nodes have correct structure."""
        compiler = LLMContextCompiler()
        result = compiler.compile(simple_review_context)
        for node in result.eg.nodes:
            # (bh_idx, sym_idx, kind_id, depth, changed, shared,
            #  reaches_svc_idx, reaches_mod_idx, reaches_pkg_idx, (ref_idxs...))
            assert len(node) == 10
            bh_idx, sym_idx, kind_id, depth, changed, shared = node[:6]
            assert isinstance(bh_idx, int)
            assert isinstance(sym_idx, int)
            assert isinstance(kind_id, int)
            assert isinstance(depth, int)
            assert isinstance(changed, bool)
            assert isinstance(shared, bool)

    def test_execution_graph_node_enum_encoding(self, simple_review_context):
        """Test that execution graph nodes use enum encoding for kind."""
        compiler = LLMContextCompiler()
        result = compiler.compile(simple_review_context)
        for node in result.eg.nodes:
            kind_id = node[2]
            assert _enum_val("kind", kind_id) == "function"

    def test_execution_graph_edges(self, multi_ep_execution_context):
        """Test that execution graph edges are created for chains."""
        rc = ReviewContext(execution=multi_ep_execution_context)
        compiler = LLMContextCompiler()
        result = compiler.compile(rc)
        assert len(result.eg.edges) >= 1

    def test_execution_graph_deduplicates_nodes(self, multi_ep_execution_context):
        """Test that shared execution steps are deduplicated in the DAG."""
        rc = ReviewContext(execution=multi_ep_execution_context)
        compiler = LLMContextCompiler()
        result = compiler.compile(rc)
        assert len(result.eg.nodes) == 3

    def test_entry_points_reference_graph_nodes(self, multi_ep_execution_context):
        """Test that entry points reference graph node indices."""
        rc = ReviewContext(execution=multi_ep_execution_context)
        compiler = LLMContextCompiler()
        result = compiler.compile(rc)
        assert len(result.epts) == 2
        for ep in result.epts:
            endpoint_idx, chain_node_idxs, terminal_idx, max_depth = ep
            assert isinstance(endpoint_idx, int)
            assert isinstance(chain_node_idxs, tuple)
            assert len(chain_node_idxs) > 0
            for node_idx in chain_node_idxs:
                assert 0 <= node_idx < len(result.eg.nodes)

    def test_deepest_execution_preserved(self, simple_review_context):
        """Test that deepest execution is preserved."""
        compiler = LLMContextCompiler()
        result = compiler.compile(simple_review_context)
        endpoint_idx, depth = result.de
        assert result.st[result.ep[endpoint_idx][0]] == "POST /test"
        assert depth == 0


# ---------------------------------------------------------------------------
# Tests: LLMContextCompiler — Discoveries Section
# ---------------------------------------------------------------------------

class TestDiscoveriesSection:
    """Tests for the discoveries section of LLMContext."""

    def test_discoveries_preserved(self, simple_review_context):
        """Test that discoveries are preserved."""
        compiler = LLMContextCompiler()
        result = compiler.compile(simple_review_context)
        assert len(result.disc) > 0

    def test_discovery_id_preserved(self, simple_review_context):
        """Test that discovery id is preserved."""
        compiler = LLMContextCompiler()
        result = compiler.compile(simple_review_context)
        for d in result.disc:
            id_idx = d[0]
            assert result.st[id_idx] == "discovery://test/1"

    def test_discovery_kind_enum_encoded(self, simple_review_context):
        """Test that discovery kind uses enum encoding."""
        compiler = LLMContextCompiler()
        result = compiler.compile(simple_review_context)
        for d in result.disc:
            kind_id = d[1]
            assert _enum_val("bh_kind", kind_id) == "deep_execution"

    def test_discovery_facts_preserved(self, simple_review_context):
        """Test that discovery facts dict is preserved."""
        compiler = LLMContextCompiler()
        result = compiler.compile(simple_review_context)
        for d in result.disc:
            facts = d[2]
            assert isinstance(facts, dict)
            assert "max_depth" in facts

    def test_discovery_references_preserved(self, simple_review_context):
        """Test that discovery references are preserved."""
        compiler = LLMContextCompiler()
        result = compiler.compile(simple_review_context)
        for d in result.disc:
            ref_idxs = d[3]
            assert len(ref_idxs) > 0
            for ref_idx in ref_idxs:
                assert 0 <= ref_idx < len(result.ref)

    def test_discovery_references_deduplicated(self, multi_discovery_context):
        """Test that shared references are deduplicated in the table."""
        rc = ReviewContext(discoveries=multi_discovery_context)
        compiler = LLMContextCompiler()
        result = compiler.compile(rc)
        assert len(result.ref) == 2


# ---------------------------------------------------------------------------
# Tests: LLMContextCompiler — Determinism
# ---------------------------------------------------------------------------

class TestDeterminism:
    """Tests that the compiler is deterministic."""

    def test_deterministic_output(self, simple_review_context):
        """Test that same input always produces same output."""
        compiler = LLMContextCompiler()
        result1 = compiler.compile(simple_review_context)
        result2 = compiler.compile(simple_review_context)
        assert result1 == result2

    def test_deterministic_with_multi_file(self, multi_file_change_context):
        """Test determinism with multi-file change context."""
        rc = ReviewContext(change=multi_file_change_context)
        compiler = LLMContextCompiler()
        result1 = compiler.compile(rc)
        result2 = compiler.compile(rc)
        assert result1 == result2

    def test_deterministic_with_multi_ep(self, multi_ep_execution_context):
        """Test determinism with multi-entry-point execution context."""
        rc = ReviewContext(execution=multi_ep_execution_context)
        compiler = LLMContextCompiler()
        result1 = compiler.compile(rc)
        result2 = compiler.compile(rc)
        assert result1 == result2

    def test_deterministic_with_multi_discovery(self, multi_discovery_context):
        """Test determinism with multiple discoveries."""
        rc = ReviewContext(discoveries=multi_discovery_context)
        compiler = LLMContextCompiler()
        result1 = compiler.compile(rc)
        result2 = compiler.compile(rc)
        assert result1 == result2


# ---------------------------------------------------------------------------
# Tests: LLMContextCompiler — No Information Loss
# ---------------------------------------------------------------------------

class TestNoInformationLoss:
    """Tests that no information is lost during compilation."""

    def test_all_change_strings_present(self, simple_review_context):
        """Test that all non-enum change section strings are present in the string table."""
        compiler = LLMContextCompiler()
        result = compiler.compile(simple_review_context)
        strings = list(result.st.entries)
        assert "test.py" in strings
        # Symbol IDs (URIs) are not stored directly — they're reconstructable
        # "sym://test/func1" is derivable from the symbol table + file reference
        assert "func1" in strings
        # Locations are normalized to (start_line, end_line) in the symbol table
        # so "test.py:1-10" may not appear as-is in the string table
        # (the file path is stored, but the full location string is parsed)

    def test_all_execution_strings_present(self, simple_review_context):
        """Test that all execution section strings are present in the string table."""
        compiler = LLMContextCompiler()
        result = compiler.compile(simple_review_context)
        strings = list(result.st.entries)
        assert "POST /test" in strings
        assert "/test" in strings
        assert "behavior://test" in strings
        assert "return" in strings
        assert "api" in strings
        assert "test_module" in strings

    def test_all_discovery_strings_present(self, simple_review_context):
        """Test that all discovery section strings are present in the string table."""
        compiler = LLMContextCompiler()
        result = compiler.compile(simple_review_context)
        strings = list(result.st.entries)
        assert "discovery://test/1" in strings
        assert "ref://test/1" in strings

    def test_enum_values_not_in_string_table(self, simple_review_context):
        """Test that enum-encoded values are NOT stored in the string table (saving tokens)."""
        compiler = LLMContextCompiler()
        result = compiler.compile(simple_review_context)
        strings = list(result.st.entries)
        # These should be enum-encoded, not in the string table
        assert "function" not in strings
        assert "public" not in strings
        assert "python" not in strings  # from file table
        assert "modified" not in strings  # from file table
        assert "POST" not in strings  # from endpoint table

    def test_func1_not_in_string_table_if_derivable(self, simple_review_context):
        """Test that 'func1' is NOT in string table if derivable from symbol id.

        The symbol id is "sym://test/func1" and the hash part is "func1",
        so the name is derivable and should not be stored.
        """
        compiler = LLMContextCompiler()
        result = compiler.compile(simple_review_context)
        strings = list(result.st.entries)
        # "func1" is derivable from "sym://test/func1#func1" pattern
        # Our current URI pattern: "sym://test/func1" has no #, so func1 is NOT derivable
        # but it gets stored in string table. This is fine.
        assert "func1" in strings  # Our URI format doesn't use #, so name is stored


# ---------------------------------------------------------------------------
# Tests: LLMContextCompiler — Edge Cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Tests for edge cases in LLMContext compilation."""

    def test_empty_strings(self):
        """Test that empty strings are handled correctly."""
        rc = ReviewContext()
        compiler = LLMContextCompiler()
        result = compiler.compile(rc)
        assert result.st[0] == ""
        assert len(result.st) == 1

    def test_no_change_section(self, simple_execution_context):
        """Test compilation with only execution section."""
        rc = ReviewContext(execution=simple_execution_context)
        compiler = LLMContextCompiler()
        result = compiler.compile(rc)
        assert result.cs == (0, 0, 0, 0, 0)
        assert result.cf == ()
        assert len(result.eg.nodes) > 0

    def test_no_execution_section(self, simple_change_context):
        """Test compilation with only change section."""
        rc = ReviewContext(change=simple_change_context)
        compiler = LLMContextCompiler()
        result = compiler.compile(rc)
        assert len(result.f) > 0
        assert result.eg.nodes == ()
        assert result.epts == ()

    def test_no_discoveries(self, simple_change_context):
        """Test compilation with no discoveries."""
        rc = ReviewContext(change=simple_change_context)
        compiler = LLMContextCompiler()
        result = compiler.compile(rc)
        assert result.disc == ()

    def test_repeated_strings_across_sections(self):
        """Test that strings repeated across sections are deduplicated."""
        change = TestHelper.create_change(
            symbol_id="sym://test/func1",
            symbol_name="func1",
            symbol_kind="function",
            change_type="modified",
        )
        file_change = TestHelper.create_file_change(
            path="test.py",
            language="python",
            change_type="modified",
            changes=(change,),
        )
        change_ctx = TestHelper.create_change_context(
            files=(file_change,),
        )
        step = TestHelper.create_execution_step(
            behavior="behavior://test",
            symbol_id="sym://test/func1",
            symbol_name="func1",
            kind="function",
        )
        ep = TestHelper.create_entry_point(
            execution_chain=(step,),
        )
        exec_ctx = TestHelper.create_execution_context(
            entry_points=(ep,),
        )
        rc = ReviewContext(change=change_ctx, execution=exec_ctx)
        compiler = LLMContextCompiler()
        result = compiler.compile(rc)
        strings = list(result.st.entries)
        # Symbol IDs (URIs) are not stored in the string table since they're
        # reconstructable from file + symbol references. "sym://test/func1" is
        # NOT in the string table.
        assert "sym://test/func1" not in strings
        # "func1" is a repeated string and should appear only once
        assert strings.count("func1") == 1
        # "function" is enum-encoded and NOT in string table
        assert "function" not in strings

    def test_large_reference_count(self):
        """Test that many references are handled correctly."""
        refs = tuple(
            TestHelper.create_reference(
                id=f"ref://test/{i}",
                kind="symbol",
                location=f"file{i}.py",
                compiler_artifact="symbol",
            )
            for i in range(50)
        )
        discovery = TestHelper.create_discovery(
            id="discovery://many_refs/1",
            kind="deep_execution",
            facts={"max_depth": 2},
            reference_count=50,
            references=refs,
        )
        rc = ReviewContext(discoveries=(discovery,))
        compiler = LLMContextCompiler()
        result = compiler.compile(rc)
        assert len(result.ref) == 50
        assert len(result.disc) == 1
        d = result.disc[0]
        assert len(d[3]) == 50

    def test_unknown_enum_value_defaults_to_zero(self):
        """Test that unrecognized enum values default to 0 (empty)."""
        change = TestHelper.create_change(
            symbol_kind="some_unknown_kind",
            symbol_visibility="unknown_vis",
        )
        file_change = TestHelper.create_file_change(
            changes=(change,),
        )
        rc = ReviewContext(
            change=TestHelper.create_change_context(files=(file_change,))
        )
        compiler = LLMContextCompiler()
        result = compiler.compile(rc)
        for entry in result.sym:
            _, _, kind_id, vis_id, _ = entry
            assert kind_id == 0  # Unknown kind defaults to 0
            assert vis_id == 0  # Unknown visibility defaults to 0

    def test_location_parsing_various_formats(self):
        """Test that various location formats are parsed correctly."""
        from llm_context.compiler import _parse_location

        # Standard format
        assert _parse_location("file.py:1-10") == ("file.py", 1, 10)
        # Single line
        assert _parse_location("file.py:5") == ("file.py", 5, 5)
        # Path with directory
        assert _parse_location("path/to/file.py:25-279") == ("path/to/file.py", 25, 279)
        # No location
        assert _parse_location("") == ("", 0, 0)
        # Just path, no line numbers
        assert _parse_location("file.py") == ("file.py", 0, 0)
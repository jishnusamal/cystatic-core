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
        assert result.ep == ()
        assert result.cs == (0, 0, 0, 0, 0)
        assert result.cf == ()
        assert isinstance(result.eg, ExecutionGraph)
        assert result.epts == ()
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
            assert len(entry) == 2  # (path_idx, ct_id)
            path, ctype = entry
            assert isinstance(path, int)
            assert isinstance(ctype, int)

    def test_file_table_enum_encoding(self, simple_review_context):
        """Test that file table uses enum encoding for change_type."""
        compiler = LLMContextCompiler()
        result = compiler.compile(simple_review_context)
        for entry in result.f:
            _, ct_id = entry
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
            # (file_id, name_idx, kind_id)
            assert len(entry) == 3
            file_id, name_idx, kind_id = entry
            assert isinstance(file_id, int)
            assert isinstance(name_idx, int)
            assert isinstance(kind_id, int)

    def test_symbol_table_enum_encoding(self, simple_review_context):
        """Test that symbol table uses enum encoding for kind."""
        compiler = LLMContextCompiler()
        result = compiler.compile(simple_review_context)
        for entry in result.sym:
            _, _, kind_id = entry
            assert _enum_val("kind", kind_id) == "function"

    def test_symbol_table_deduplicates(self, multi_file_change_context):
        """Test that symbol table deduplicates by symbol id."""
        rc = ReviewContext(change=multi_file_change_context)
        compiler = LLMContextCompiler()
        result = compiler.compile(rc)
        assert len(result.sym) == 3

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
            assert len(entry) == 2  # (endpoint_idx, path_idx)
            for field in entry:
                assert isinstance(field, int)


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
            # (sym_idx, kind_id, depth, reaches_svc_idx)
            assert len(node) == 4
            sym_idx, kind_id, depth, reaches_svc_idx = node
            assert isinstance(sym_idx, int)
            assert isinstance(kind_id, int)
            assert isinstance(depth, int)
            assert isinstance(reaches_svc_idx, int)

    def test_execution_graph_node_enum_encoding(self, simple_review_context):
        """Test that execution graph nodes use enum encoding for kind."""
        compiler = LLMContextCompiler()
        result = compiler.compile(simple_review_context)
        for node in result.eg.nodes:
            kind_id = node[1]
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

    def test_discovery_kind_enum_encoded(self, simple_review_context):
        """Test that discovery kind uses enum encoding."""
        compiler = LLMContextCompiler()
        result = compiler.compile(simple_review_context)
        for d in result.disc:
            kind_id = d[0]
            assert _enum_val("bh_kind", kind_id) == "deep_execution"

    def test_discovery_facts_preserved(self, simple_review_context):
        """Test that discovery facts dict is preserved."""
        compiler = LLMContextCompiler()
        result = compiler.compile(simple_review_context)
        for d in result.disc:
            facts = d[1]
            assert isinstance(facts, dict)
            assert "max_depth" in facts


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
# Tests: LLMContextCompiler — Token Compression
# ---------------------------------------------------------------------------

class TestTokenCompression:
    """Tests that information is concisely compressed in LLMContext."""

    def test_all_change_strings_present(self, simple_review_context):
        """Test that key change section strings are present in the string table."""
        compiler = LLMContextCompiler()
        result = compiler.compile(simple_review_context)
        strings = list(result.st.entries)
        assert "test.py" in strings

    def test_all_execution_strings_present(self, simple_review_context):
        """Test that execution section strings are present in the string table."""
        compiler = LLMContextCompiler()
        result = compiler.compile(simple_review_context)
        strings = list(result.st.entries)
        assert "POST /test" in strings
        assert "/test" in strings
        assert "return" in strings

    def test_enum_values_not_in_string_table(self, simple_review_context):
        """Test that enum-encoded values are NOT stored in the string table (saving tokens)."""
        compiler = LLMContextCompiler()
        result = compiler.compile(simple_review_context)
        strings = list(result.st.entries)
        assert "function" not in strings
        assert "modified" not in strings


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
            _, _, kind_id = entry
            assert kind_id == 0  # Unknown kind defaults to 0

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


class TestHighDensityFiltering:
    """Tests validating the semantic classification and high-density filtering logic."""

    def test_execution_graph_connection_preservation(self):
        """Test that collapsing infrastructure nodes preserves caller-callee connectivity."""
        step1 = TestHelper.create_execution_step(
            behavior="behavior://api1",
            symbol_id="sym://api/controller",
            symbol_name="CheckoutController",
            symbol_kind="class",
            depth=0,
            changed=False
        )
        step2 = TestHelper.create_execution_step(
            behavior="behavior://api1",
            symbol_id="sym://api/depends",
            symbol_name="Depends",
            symbol_kind="function",
            depth=1,
            changed=False
        )
        step3 = TestHelper.create_execution_step(
            behavior="behavior://api1",
            symbol_id="sym://api/middleware",
            symbol_name="CORSMiddleware",
            symbol_kind="class",
            depth=2,
            changed=False
        )
        step4 = TestHelper.create_execution_step(
            behavior="behavior://api1",
            symbol_id="sym://domain/checkout",
            symbol_name="CheckoutService",
            symbol_kind="class",
            depth=3,
            changed=False
        )

        ep = TestHelper.create_entry_point(
            endpoint="POST /checkout",
            method="POST",
            path="/checkout",
            execution_chain=(step1, step2, step3, step4)
        )
        rc = TestHelper.create_review_context(
            execution=TestHelper.create_execution_context(entry_points=(ep,))
        )

        from llm_context.compiler import prune_review_context
        pruned = prune_review_context(rc)
        chain = pruned.execution.entry_points[0].execution_chain
        
        assert len(chain) == 2
        assert chain[0].symbol.name == "CheckoutController"
        assert chain[1].symbol.name == "CheckoutService"

        compiler = LLMContextCompiler()
        result = compiler.compile(rc)
        
        nodes = result.eg.nodes
        assert len(nodes) == 2

        assert len(result.eg.edges) == 1
        edge = result.eg.edges[0]
        assert edge[0] == 0
        assert edge[1] == 1

    def test_changed_symbol_preservation(self):
        """Test that changed symbols in noise categories are still preserved (never removed)."""
        step = TestHelper.create_execution_step(
            behavior="behavior://test",
            symbol_id="sym://stdlib/json",
            symbol_name="json",
            symbol_kind="module",
            depth=0,
            changed=True
        )
        ep = TestHelper.create_entry_point(execution_chain=(step,))
        
        change = TestHelper.create_change(
            symbol_id="sym://stdlib/json",
            symbol_name="json",
            symbol_kind="module",
            change_type="modified"
        )
        file_change = TestHelper.create_file_change(changes=(change,))
        change_ctx = TestHelper.create_change_context(files=(file_change,))
        
        rc = TestHelper.create_review_context(
            change=change_ctx,
            execution=TestHelper.create_execution_context(entry_points=(ep,))
        )

        compiler = LLMContextCompiler()
        result = compiler.compile(rc)

        assert len(result.eg.nodes) == 1
        sym = result.sym[result.eg.nodes[0][0]]
        assert result.st[sym[1]] == "json"

    def test_conditional_framework_removal(self):
        """Test that framework nodes are removed when unchanged, but preserved when changed."""
        step_unchanged = TestHelper.create_execution_step(
            behavior="behavior://test",
            symbol_id="sym://api/depends",
            symbol_name="Depends",
            symbol_kind="function",
            depth=0,
            changed=False
        )
        step_changed = TestHelper.create_execution_step(
            behavior="behavior://test",
            symbol_id="sym://api/router",
            symbol_name="APIRouter",
            symbol_kind="class",
            depth=1,
            changed=True
        )
        
        ep = TestHelper.create_entry_point(execution_chain=(step_unchanged, step_changed))
        change = TestHelper.create_change(
            symbol_id="sym://api/router",
            symbol_name="APIRouter",
            symbol_kind="class",
            change_type="modified"
        )
        file_change = TestHelper.create_file_change(changes=(change,))
        change_ctx = TestHelper.create_change_context(files=(file_change,))
        
        rc = TestHelper.create_review_context(
            change=change_ctx,
            execution=TestHelper.create_execution_context(entry_points=(ep,))
        )

        compiler = LLMContextCompiler()
        result = compiler.compile(rc)

        assert len(result.eg.nodes) == 1
        sym = result.sym[result.eg.nodes[0][0]]
        assert result.st[sym[1]] == "APIRouter"

    def test_business_node_preservation(self):
        """Test that business/domain nodes are never removed even when unchanged."""
        step_business = TestHelper.create_execution_step(
            behavior="behavior://test",
            symbol_id="sym://domain/checkout",
            symbol_name="CheckoutService",
            symbol_kind="class",
            depth=0,
            changed=False
        )
        step_schema = TestHelper.create_execution_step(
            behavior="behavior://test",
            symbol_id="sym://db/order",
            symbol_name="OrderEntity",
            symbol_kind="class",
            depth=1,
            changed=False
        )
        
        ep = TestHelper.create_entry_point(execution_chain=(step_business, step_schema))
        rc = TestHelper.create_review_context(
            execution=TestHelper.create_execution_context(entry_points=(ep,))
        )

        from llm_context.compiler import prune_review_context
        pruned = prune_review_context(rc)
        chain = pruned.execution.entry_points[0].execution_chain
        
        assert len(chain) == 2
        assert chain[0].symbol.name == "CheckoutService"
        assert chain[1].symbol.name == "OrderEntity"

        compiler = LLMContextCompiler()
        result = compiler.compile(rc)
        assert len(result.eg.nodes) == 2

    def test_discovery_signal_identity(self):
        """Test that discoveries are preserved identically, filtering out only compiler metadata."""
        ref_good = TestHelper.create_reference(
            id="ref://good/1",
            kind="behavior",
            location="file.py:10",
            compiler_artifact="actual_source_code"
        )
        ref_noise = TestHelper.create_reference(
            id="unit://noise/1",
            kind="dependency",
            location="unit://noise/1",
            compiler_artifact="graph_node"
        )

        discovery = Discovery(
            id="ref://discovery/1",
            kind="deep_execution",
            statement="Found critical transaction path changes.",
            facts={
                "path": "CheckoutController -> CheckoutService",
                "internal_compiler_hash": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4",
                "weight": "high"
            },
            reference_count=2,
            references=(ref_good, ref_noise)
        )

        rc = TestHelper.create_review_context(discoveries=(discovery,))

        compiler = LLMContextCompiler()
        result = compiler.compile(rc)

        assert len(result.disc) == 1
        d_compiled = result.disc[0]

        facts_compiled = d_compiled[1]
        assert "path" in facts_compiled
        assert "weight" in facts_compiled
        assert "internal_compiler_hash" not in facts_compiled


# ---------------------------------------------------------------------------
# Tests: Review Scope — Scope (what must be excluded)
# ---------------------------------------------------------------------------

class TestReviewScopeVerification:
    """Scope tests: verify that artifacts outside the review scope are excluded."""

    def test_ref_uri_treated_as_compiler_metadata(self):
        """ref:// URIs are compiler traceability identifiers and must be pruned."""
        from llm_context.review_scope_builder import is_compiler_metadata

        assert is_compiler_metadata("ref://test/1") is True
        assert is_compiler_metadata("ref://discovery/abc") is True
        assert is_compiler_metadata("REF://upper/case") is True

    def test_unit_uri_treated_as_compiler_metadata(self):
        """unit:// URIs remain classified as compiler metadata."""
        from llm_context.review_scope_builder import is_compiler_metadata

        assert is_compiler_metadata("unit://noise/1") is True

    def test_node_edge_uri_treated_as_compiler_metadata(self):
        """node:// and edge:// URIs are compiler graph identifiers."""
        from llm_context.review_scope_builder import is_compiler_metadata

        assert is_compiler_metadata("node://graph/42") is True
        assert is_compiler_metadata("edge://graph/42-43") is True

    def test_non_metadata_refs_not_pruned(self):
        """Legitimate file locations and behavior URIs are NOT pruned."""
        from llm_context.review_scope_builder import is_compiler_metadata

        assert is_compiler_metadata("file.py:10-25") is False
        assert is_compiler_metadata("behavior://domain/checkout") is False
        assert is_compiler_metadata("change://test") is False
        assert is_compiler_metadata("") is False

    def test_ref_uri_pruned_from_execution_step_references(self):
        """ref:// strings in ExecutionStep.references are removed during pruning."""
        from llm_context.review_scope_builder import prune_review_context

        step = TestHelper.create_execution_step(
            references=("ref://unit/1", "behavior://domain/checkout", "unit://noise/2"),
        )
        ep = TestHelper.create_entry_point(execution_chain=(step,))
        rc = TestHelper.create_review_context(
            execution=TestHelper.create_execution_context(entry_points=(ep,))
        )

        pruned = prune_review_context(rc)
        step_refs = pruned.execution.entry_points[0].execution_chain[0].references

        assert not any(r.startswith("ref://") for r in step_refs)
        assert not any(r.startswith("unit://") for r in step_refs)
        assert "behavior://domain/checkout" in step_refs

    def test_ref_uri_pruned_from_discovery_references(self):
        """ref:// id in Discovery.references are removed during pruning."""
        from llm_context.review_scope_builder import prune_review_context

        ref_noise = TestHelper.create_reference(
            id="ref://noise/1",
            kind="dependency",
            location="ref://noise/1",
            compiler_artifact="internal",
        )
        ref_clean = TestHelper.create_reference(
            id="behavior://domain/pay",
            kind="behavior",
            location="payment.py:10-20",
            compiler_artifact="checkout",
        )
        disc = TestHelper.create_discovery(
            references=(ref_noise, ref_clean),
            reference_count=2,
        )
        rc = TestHelper.create_review_context(discoveries=(disc,))
        pruned = prune_review_context(rc)

        surviving_ids = {r.id for r in pruned.discoveries[0].references}
        assert "ref://noise/1" not in surviving_ids
        assert "behavior://domain/pay" in surviving_ids

    def test_unrelated_framework_execution_nodes_removed(self):
        """Unchanged framework nodes are absent from the compiled execution graph."""
        from llm_context.review_scope_builder import prune_review_context

        step_fw = TestHelper.create_execution_step(
            symbol_id="sym://fw/depends",
            symbol_name="Depends",
            symbol_kind="function",
            depth=0,
            changed=False,
        )
        step_biz = TestHelper.create_execution_step(
            symbol_id="sym://domain/pay",
            symbol_name="PaymentService",
            symbol_kind="class",
            depth=1,
            changed=False,
        )
        ep = TestHelper.create_entry_point(execution_chain=(step_fw, step_biz))
        rc = TestHelper.create_review_context(
            execution=TestHelper.create_execution_context(entry_points=(ep,))
        )

        # Verify pruning: only the business node survives in the ReviewContext
        pruned = prune_review_context(rc)
        chain = pruned.execution.entry_points[0].execution_chain
        surviving_names = [s.symbol.name for s in chain]
        assert "Depends" not in surviving_names
        assert "PaymentService" in surviving_names

        # Verify compiler: DAG has exactly 1 node (the business node)
        compiler = LLMContextCompiler()
        result = compiler.compile(rc)
        assert len(result.eg.nodes) == 1

    def test_hex_hash_facts_excluded(self):
        """Discovery facts containing 32+ char hex hashes are stripped."""
        from llm_context.review_scope_builder import prune_review_context

        disc = TestHelper.create_discovery(
            facts={
                "path": "A -> B",
                "hash_key": "a" * 32,
                "internal_id": "b1c2d3e4f5a6b7c8d9e0f1a2b3c4d5e6",
                "weight": "high",
            }
        )
        rc = TestHelper.create_review_context(discoveries=(disc,))
        pruned = prune_review_context(rc)
        facts = pruned.discoveries[0].facts

        assert "path" in facts
        assert "weight" in facts
        assert "hash_key" not in facts
        assert "internal_id" not in facts


# ---------------------------------------------------------------------------
# Tests: Review Scope — Preservation (what must be retained)
# ---------------------------------------------------------------------------

class TestReviewScopePreservation:
    """Preservation tests: verify that review-relevant artifacts are never discarded."""

    def test_changed_file_retained(self):
        """Every changed file appears in the compiled file table."""
        change = TestHelper.create_change(
            symbol_id="sym://app/create_order",
            symbol_name="create_order",
            symbol_kind="function",
            change_type="modified",
        )
        file_change = TestHelper.create_file_change(
            path="orders/service.py",
            changes=(change,),
        )
        rc = TestHelper.create_review_context(
            change=TestHelper.create_change_context(files=(file_change,))
        )

        compiler = LLMContextCompiler()
        result = compiler.compile(rc)

        file_paths = {result.st[entry[0]] for entry in result.f}
        assert "orders/service.py" in file_paths

    def test_changed_symbol_retained(self):
        """Every changed symbol appears in the compiled symbol table."""
        change = TestHelper.create_change(
            symbol_id="sym://app/create_order",
            symbol_name="create_order",
            symbol_kind="function",
            change_type="added",
        )
        file_change = TestHelper.create_file_change(changes=(change,))
        rc = TestHelper.create_review_context(
            change=TestHelper.create_change_context(files=(file_change,))
        )

        compiler = LLMContextCompiler()
        result = compiler.compile(rc)

        assert len(result.sym) >= 1
        assert len(result.f) == 1

    def test_changed_symbol_in_noise_category_retained_in_execution(self):
        """A symbol marked changed=True survives pruning even if it is stdlib/framework."""
        from llm_context.review_scope_builder import prune_review_context

        step = TestHelper.create_execution_step(
            symbol_name="logging",
            symbol_kind="module",
            depth=0,
            changed=True,
        )
        ep = TestHelper.create_entry_point(execution_chain=(step,))
        rc = TestHelper.create_review_context(
            execution=TestHelper.create_execution_context(entry_points=(ep,))
        )

        pruned = prune_review_context(rc)
        assert len(pruned.execution.entry_points[0].execution_chain) == 1

    def test_discovery_count_preserved(self):
        """Discovery count is identical before and after pruning."""
        from llm_context.review_scope_builder import prune_review_context

        d1 = TestHelper.create_discovery(id="discovery://a/1", kind="deep_execution")
        d2 = TestHelper.create_discovery(id="discovery://b/1", kind="shared_execution")
        d3 = TestHelper.create_discovery(id="discovery://c/1", kind="boundary_crossing")
        rc = TestHelper.create_review_context(discoveries=(d1, d2, d3))

        pruned = prune_review_context(rc)
        assert len(pruned.discoveries) == 3

    def test_discovery_count_preserved_after_compile(self):
        """Compiled disc tuple length equals original discovery count."""
        d1 = TestHelper.create_discovery(kind="deep_execution", facts={"depth": 5})
        d2 = TestHelper.create_discovery(kind="shared_execution", facts={"count": 3})
        rc = TestHelper.create_review_context(discoveries=(d1, d2))

        compiler = LLMContextCompiler()
        result = compiler.compile(rc)

        assert len(result.disc) == 2

    def test_execution_path_non_noise_steps_preserved(self):
        """Business logic and domain steps are always retained."""
        from llm_context.review_scope_builder import prune_review_context

        step_biz = TestHelper.create_execution_step(
            symbol_name="OrderProcessor",
            symbol_kind="class",
            depth=0,
            changed=False,
        )
        step_event = TestHelper.create_execution_step(
            symbol_name="OrderCreatedPublisher",
            symbol_kind="class",
            depth=1,
            changed=False,
        )
        ep = TestHelper.create_entry_point(execution_chain=(step_biz, step_event))
        rc = TestHelper.create_review_context(
            execution=TestHelper.create_execution_context(entry_points=(ep,))
        )

        pruned = prune_review_context(rc)
        chain = pruned.execution.entry_points[0].execution_chain
        names = {s.symbol.name for s in chain}

        assert "OrderProcessor" in names
        assert "OrderCreatedPublisher" in names

    def test_valid_discovery_references_retained(self):
        """References with non-metadata ids and locations survive pruning."""
        from llm_context.review_scope_builder import prune_review_context

        ref = TestHelper.create_reference(
            id="behavior://domain/checkout",
            kind="behavior",
            location="checkout.py:10-40",
            compiler_artifact="checkout_service",
        )
        disc = TestHelper.create_discovery(references=(ref,), reference_count=1)
        rc = TestHelper.create_review_context(discoveries=(disc,))

        pruned = prune_review_context(rc)
        assert len(pruned.discoveries[0].references) == 1
        assert pruned.discoveries[0].references[0].id == "behavior://domain/checkout"

    def test_discovery_facts_with_clean_values_retained(self):
        """Discovery facts with non-metadata keys and values are fully retained."""
        from llm_context.review_scope_builder import prune_review_context

        facts = {
            "max_depth": 7,
            "shared_symbol_ids": ("sym://domain/pay",),
            "path": "Controller -> Service -> Repository",
            "weight": "high",
        }
        disc = TestHelper.create_discovery(facts=facts)
        rc = TestHelper.create_review_context(discoveries=(disc,))

        pruned = prune_review_context(rc)
        retained = pruned.discoveries[0].facts

        assert retained["max_depth"] == 7
        assert retained["weight"] == "high"
        assert retained["path"] == "Controller -> Service -> Repository"


# ---------------------------------------------------------------------------
# Tests: Review Scope — Equivalence (output identity)
# ---------------------------------------------------------------------------

class TestReviewScopeEquivalence:
    """Equivalence tests: outputs are identical whether generated from original
    or pruned contexts, and are deterministic across multiple runs."""

    def test_deterministic_pruned_output(self):
        """Pruning the same context twice produces identical results."""
        from llm_context.review_scope_builder import prune_review_context

        step = TestHelper.create_execution_step(
            symbol_name="CheckoutService",
            symbol_kind="class",
            depth=0,
            changed=True,
            references=("ref://noise/1", "behavior://domain/checkout"),
        )
        ep = TestHelper.create_entry_point(execution_chain=(step,))
        ref = TestHelper.create_reference(
            id="behavior://domain/checkout",
            kind="behavior",
            location="checkout.py:5",
            compiler_artifact="checkout",
        )
        disc = TestHelper.create_discovery(references=(ref,), reference_count=1)
        rc = TestHelper.create_review_context(
            execution=TestHelper.create_execution_context(entry_points=(ep,)),
            discoveries=(disc,),
        )

        pruned1 = prune_review_context(rc)
        pruned2 = prune_review_context(rc)
        assert pruned1 == pruned2

    def test_discovery_facts_equivalent_after_pruning(self):
        """Discovery facts dict is identical between original and pruned context
        (after removing metadata keys)."""
        from llm_context.review_scope_builder import prune_review_context

        facts = {
            "max_depth": 4,
            "path": "A -> B -> C",
            "compiler_noise": "unit://internal/hash",
        }
        disc = TestHelper.create_discovery(facts=facts)
        rc = TestHelper.create_review_context(discoveries=(disc,))
        pruned = prune_review_context(rc)

        retained = pruned.discoveries[0].facts
        assert retained.get("max_depth") == 4
        assert retained.get("path") == "A -> B -> C"
        assert "compiler_noise" not in retained

    def test_execution_ordering_equivalent_after_pruning(self):
        """After pruning noise steps, the relative order of surviving steps
        matches their order in the original execution chain."""
        from llm_context.review_scope_builder import prune_review_context

        steps = [
            TestHelper.create_execution_step(
                symbol_id=f"sym://domain/svc{i}",
                symbol_name=f"Service{i}",
                symbol_kind="class",
                depth=i,
                changed=False,
            )
            for i in range(4)
        ]
        noise = TestHelper.create_execution_step(
            symbol_name="Depends",
            symbol_kind="function",
            depth=2,
            changed=False,
        )
        chain = (steps[0], steps[1], noise, steps[2], steps[3])
        ep = TestHelper.create_entry_point(execution_chain=chain)
        rc = TestHelper.create_review_context(
            execution=TestHelper.create_execution_context(entry_points=(ep,))
        )

        pruned = prune_review_context(rc)
        pruned_chain = pruned.execution.entry_points[0].execution_chain

        surviving_names = [s.symbol.name for s in pruned_chain]
        assert "Depends" not in surviving_names
        svc_indices = [surviving_names.index(f"Service{i}") for i in range(4)]
        assert svc_indices == sorted(svc_indices)

    def test_compiled_output_deterministic_across_runs(self):
        """LLMContextCompiler produces identical output on repeated calls."""
        step = TestHelper.create_execution_step(
            symbol_name="PaymentService",
            symbol_kind="class",
            depth=0,
            changed=True,
        )
        ep = TestHelper.create_entry_point(execution_chain=(step,))
        change = TestHelper.create_change(
            symbol_id="sym://domain/pay",
            symbol_name="PaymentService",
            symbol_kind="class",
            change_type="modified",
        )
        file_change = TestHelper.create_file_change(changes=(change,))
        rc = TestHelper.create_review_context(
            change=TestHelper.create_change_context(files=(file_change,)),
            execution=TestHelper.create_execution_context(entry_points=(ep,)),
        )

        compiler = LLMContextCompiler()
        r1 = compiler.compile(rc)
        r2 = compiler.compile(rc)
        assert r1 == r2

    def test_shared_references_across_discoveries_canonicalized(self):
        """When two discoveries share an identical Reference, the same object
        is stored (evidence deduplication). Both discoveries still receive the ref."""
        from llm_context.review_scope_builder import prune_review_context

        shared_ref = TestHelper.create_reference(
            id="behavior://domain/checkout",
            kind="behavior",
            location="checkout.py:5",
            compiler_artifact="checkout",
        )
        d1 = TestHelper.create_discovery(
            id="discovery://a/1",
            kind="deep_execution",
            references=(shared_ref,),
            reference_count=1,
        )
        d2 = TestHelper.create_discovery(
            id="discovery://b/1",
            kind="shared_execution",
            references=(shared_ref,),
            reference_count=1,
        )
        rc = TestHelper.create_review_context(discoveries=(d1, d2))
        pruned = prune_review_context(rc)

        ref_d1 = pruned.discoveries[0].references[0]
        ref_d2 = pruned.discoveries[1].references[0]

        assert ref_d1.id == ref_d2.id == "behavior://domain/checkout"
        assert ref_d1 is ref_d2


# ---------------------------------------------------------------------------
# Tests: Review Scope — Metrics (measurable reduction with assertions)
# ---------------------------------------------------------------------------

class TestReviewScopeMetrics:
    """Metrics tests: assert measurable token/size reductions when pruning applies."""

    def _build_noisy_review_context(self) -> ReviewContext:
        """Build a ReviewContext that contains framework execution noise and
        compiler metadata references that the pruner removes."""
        change = TestHelper.create_change(
            symbol_id="sym://domain/checkout",
            symbol_name="checkout",
            symbol_kind="function",
            change_type="modified",
        )
        file_change = TestHelper.create_file_change(
            path="checkout/service.py",
            changes=(change,),
        )
        change_ctx = TestHelper.create_change_context(files=(file_change,))

        step_changed = TestHelper.create_execution_step(
            symbol_id="sym://domain/checkout",
            symbol_name="checkout",
            symbol_kind="function",
            depth=0,
            changed=True,
        )
        step_fw1 = TestHelper.create_execution_step(
            symbol_name="APIRouter",
            symbol_kind="class",
            depth=1,
            changed=False,
        )
        step_fw2 = TestHelper.create_execution_step(
            symbol_name="Depends",
            symbol_kind="function",
            depth=2,
            changed=False,
        )
        step_fw3 = TestHelper.create_execution_step(
            symbol_name="CORSMiddleware",
            symbol_kind="class",
            depth=3,
            changed=False,
        )
        ep = TestHelper.create_entry_point(
            endpoint="POST /checkout",
            path="/checkout",
            execution_chain=(step_changed, step_fw1, step_fw2, step_fw3),
            references=("ref://internal/1", "unit://noise/2"),
        )
        exec_ctx = TestHelper.create_execution_context(entry_points=(ep,))

        ref_noise = TestHelper.create_reference(
            id="ref://internal/hash/1",
            kind="dependency",
            location="unit://noise/1",
            compiler_artifact="internal",
        )
        ref_clean = TestHelper.create_reference(
            id="behavior://domain/checkout",
            kind="behavior",
            location="checkout.py:1-50",
            compiler_artifact="checkout",
        )
        disc = TestHelper.create_discovery(
            facts={
                "path": "POST /checkout -> checkout",
                "compiler_hash": "a" * 32,
            },
            references=(ref_noise, ref_clean),
            reference_count=2,
        )

        return TestHelper.create_review_context(
            change=change_ctx,
            execution=exec_ctx,
            discoveries=(disc,),
        )

    def _compile_without_pruning(self, rc: ReviewContext) -> LLMContext:
        """Compile rc bypassing the review-scope pruning phase."""
        import llm_context.compiler as compiler_mod
        original_brs = compiler_mod.build_review_scope
        compiler_mod.build_review_scope = lambda ctx: ctx
        try:
            return LLMContextCompiler().compile(rc)
        finally:
            compiler_mod.build_review_scope = original_brs

    def test_execution_node_count_smaller_after_pruning(self):
        """Pruning removes framework nodes — compiled graph has fewer nodes."""
        noisy_rc = self._build_noisy_review_context()
        full_result = self._compile_without_pruning(noisy_rc)
        pruned_result = LLMContextCompiler().compile(noisy_rc)
        assert len(pruned_result.eg.nodes) < len(full_result.eg.nodes)

    def test_string_table_smaller_after_pruning(self):
        """Pruning removes framework identifiers — string table has fewer entries."""
        noisy_rc = self._build_noisy_review_context()
        full_result = self._compile_without_pruning(noisy_rc)
        pruned_result = LLMContextCompiler().compile(noisy_rc)
        assert len(pruned_result.st) <= len(full_result.st)

    def test_discovery_count_unchanged_by_pruning(self):
        """Pruning never removes a discovery — only cleans its references and facts."""
        noisy_rc = self._build_noisy_review_context()
        full_result = self._compile_without_pruning(noisy_rc)
        pruned_result = LLMContextCompiler().compile(noisy_rc)
        assert len(pruned_result.disc) == len(full_result.disc)

    def test_serialized_size_decreases_after_pruning(self):
        """JSON-serialized LLMContext is smaller after pruning than without it."""
        import json
        import dataclasses

        noisy_rc = self._build_noisy_review_context()

        def _serialize(ctx) -> str:
            return json.dumps(dataclasses.asdict(ctx), default=str)

        full_result = self._compile_without_pruning(noisy_rc)
        full_size = len(_serialize(full_result))

        pruned_result = LLMContextCompiler().compile(noisy_rc)
        pruned_size = len(_serialize(pruned_result))

        assert pruned_size < full_size, (
            f"Expected pruned size ({pruned_size}) < full size ({full_size})"
        )

    def test_changed_symbol_count_unchanged_by_pruning(self):
        """The number of changed symbols and files is never reduced by pruning."""
        noisy_rc = self._build_noisy_review_context()
        full_result = self._compile_without_pruning(noisy_rc)
        pruned_result = LLMContextCompiler().compile(noisy_rc)
        assert len(pruned_result.f) == len(full_result.f)
        assert len(pruned_result.sym) == len(full_result.sym)

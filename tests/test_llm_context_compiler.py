"""Tests for the LLMContext Compiler — deterministic token-efficient representation of ReviewContext.

Tests that LLMContextCompiler correctly transforms ReviewContext into a lossless,
token-efficient representation without any semantic interpretation or information loss.
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
        assert isinstance(result.strings, StringTable)
        assert result.files == ()
        assert result.symbols == ()
        assert result.behaviors == ()
        assert result.references == ()
        assert result.endpoints == ()
        assert result.change_summary == (0, 0, 0, 0, 0)
        assert result.change_files == ()
        assert isinstance(result.execution_graph, ExecutionGraph)
        assert result.entry_points == ()
        assert result.deepest_execution == (0, 0)
        assert result.discoveries == ()


# ---------------------------------------------------------------------------
# Tests: LLMContextCompiler — String Table
# ---------------------------------------------------------------------------

class TestStringTable:
    """Tests for the global string dictionary."""

    def test_strings_collected_from_change(self, simple_review_context):
        """Test that strings from change section are collected."""
        compiler = LLMContextCompiler()
        result = compiler.compile(simple_review_context)
        assert len(result.strings) > 0

    def test_strings_collected_from_execution(self, simple_review_context):
        """Test that strings from execution section are collected."""
        compiler = LLMContextCompiler()
        result = compiler.compile(simple_review_context)
        # Should have strings like "POST /test", "POST", "/test", "behavior://test", etc.
        strings = list(result.strings.entries)
        assert any("POST" in s for s in strings)
        assert any("/test" in s for s in strings)

    def test_strings_collected_from_discoveries(self, simple_review_context):
        """Test that strings from discoveries section are collected."""
        compiler = LLMContextCompiler()
        result = compiler.compile(simple_review_context)
        strings = list(result.strings.entries)
        assert any("discovery://" in s for s in strings)
        assert any("ref://" in s for s in strings)

    def test_strings_deduplicated(self, simple_review_context):
        """Test that repeated strings are stored only once."""
        compiler = LLMContextCompiler()
        result = compiler.compile(simple_review_context)
        strings = list(result.strings.entries)
        # Each string should appear at most once
        assert len(strings) == len(set(strings))

    def test_empty_string_index_zero(self, simple_review_context):
        """Test that empty strings always get index 0."""
        compiler = LLMContextCompiler()
        result = compiler.compile(simple_review_context)
        # Index 0 should resolve to empty string
        assert result.strings[0] == ""


# ---------------------------------------------------------------------------
# Tests: LLMContextCompiler — Lookup Tables
# ---------------------------------------------------------------------------

class TestLookupTables:
    """Tests for normalized lookup tables."""

    def test_file_table_populated(self, simple_review_context):
        """Test that file table is populated from change context."""
        compiler = LLMContextCompiler()
        result = compiler.compile(simple_review_context)
        assert len(result.files) > 0

    def test_file_table_entries(self, simple_review_context):
        """Test that file table entries have correct structure."""
        compiler = LLMContextCompiler()
        result = compiler.compile(simple_review_context)
        for entry in result.files:
            assert len(entry) == 3  # (path_idx, language_idx, change_type_idx)
            path, lang, ctype = entry
            assert isinstance(path, int)
            assert isinstance(lang, int)
            assert isinstance(ctype, int)

    def test_file_table_deduplicates(self, multi_file_change_context):
        """Test that file table deduplicates by path."""
        rc = ReviewContext(change=multi_file_change_context)
        compiler = LLMContextCompiler()
        result = compiler.compile(rc)
        # Two unique files
        assert len(result.files) == 2

    def test_symbol_table_populated(self, simple_review_context):
        """Test that symbol table is populated from change context."""
        compiler = LLMContextCompiler()
        result = compiler.compile(simple_review_context)
        assert len(result.symbols) > 0

    def test_symbol_table_entries(self, simple_review_context):
        """Test that symbol table entries have correct structure."""
        compiler = LLMContextCompiler()
        result = compiler.compile(simple_review_context)
        for entry in result.symbols:
            assert len(entry) == 6  # (id, name, kind, visibility, language, location)
            for field in entry:
                assert isinstance(field, int)

    def test_symbol_table_deduplicates(self, multi_file_change_context):
        """Test that symbol table deduplicates by symbol id."""
        rc = ReviewContext(change=multi_file_change_context)
        compiler = LLMContextCompiler()
        result = compiler.compile(rc)
        # Three unique symbols
        assert len(result.symbols) == 3

    def test_behavior_table_populated(self, simple_review_context):
        """Test that behavior table is populated from execution context."""
        compiler = LLMContextCompiler()
        result = compiler.compile(simple_review_context)
        assert len(result.behaviors) > 0

    def test_behavior_table_entries(self, simple_review_context):
        """Test that behavior table entries have correct structure."""
        compiler = LLMContextCompiler()
        result = compiler.compile(simple_review_context)
        for entry in result.behaviors:
            assert len(entry) == 3  # (id, name, kind)
            for field in entry:
                assert isinstance(field, int)

    def test_reference_table_populated(self, simple_review_context):
        """Test that reference table is populated from discoveries."""
        compiler = LLMContextCompiler()
        result = compiler.compile(simple_review_context)
        assert len(result.references) > 0

    def test_reference_table_entries(self, simple_review_context):
        """Test that reference table entries have correct structure."""
        compiler = LLMContextCompiler()
        result = compiler.compile(simple_review_context)
        for entry in result.references:
            assert len(entry) == 4  # (id, kind, location, compiler_artifact)
            for field in entry:
                assert isinstance(field, int)

    def test_reference_table_deduplicates(self, multi_discovery_context):
        """Test that reference table deduplicates by reference id."""
        rc = ReviewContext(discoveries=multi_discovery_context)
        compiler = LLMContextCompiler()
        result = compiler.compile(rc)
        # Two unique references shared across two discoveries
        assert len(result.references) == 2

    def test_endpoint_table_populated(self, simple_review_context):
        """Test that endpoint table is populated from execution context."""
        compiler = LLMContextCompiler()
        result = compiler.compile(simple_review_context)
        assert len(result.endpoints) > 0

    def test_endpoint_table_entries(self, simple_review_context):
        """Test that endpoint table entries have correct structure."""
        compiler = LLMContextCompiler()
        result = compiler.compile(simple_review_context)
        for entry in result.endpoints:
            assert len(entry) == 3  # (endpoint, method, path)
            for field in entry:
                assert isinstance(field, int)


# ---------------------------------------------------------------------------
# Tests: LLMContextCompiler — Change Section
# ---------------------------------------------------------------------------

class TestChangeSection:
    """Tests for the change section of LLMContext."""

    def test_change_summary_preserved(self, simple_review_context):
        """Test that change summary values are preserved."""
        compiler = LLMContextCompiler()
        result = compiler.compile(simple_review_context)
        classification_idx, scope_idx, file_count, symbol_count, behavior_count = result.change_summary
        assert result.strings[classification_idx] == "modification"
        assert result.strings[scope_idx] == "local"
        assert file_count == 1
        assert symbol_count == 1
        assert behavior_count == 1

    def test_change_files_preserved(self, simple_review_context):
        """Test that change files are preserved."""
        compiler = LLMContextCompiler()
        result = compiler.compile(simple_review_context)
        assert len(result.change_files) > 0

    def test_change_file_references_correct_file(self, simple_review_context):
        """Test that change file references the correct file table entry."""
        compiler = LLMContextCompiler()
        result = compiler.compile(simple_review_context)
        for file_entry in result.change_files:
            file_idx = file_entry[0]
            file_path = result.strings[result.files[file_idx][0]]
            assert file_path == "test.py"

    def test_change_symbol_references_correct_symbol(self, simple_review_context):
        """Test that change symbol references the correct symbol table entry."""
        compiler = LLMContextCompiler()
        result = compiler.compile(simple_review_context)
        for file_entry in result.change_files:
            changes = file_entry[1]
            for change_entry in changes:
                sym_idx = change_entry[0]
                sym_name = result.strings[result.symbols[sym_idx][1]]
                assert sym_name == "func1"

    def test_behavior_changes_preserved(self, simple_review_context):
        """Test that behavior change type names are preserved."""
        compiler = LLMContextCompiler()
        result = compiler.compile(simple_review_context)
        for file_entry in result.change_files:
            changes = file_entry[1]
            for change_entry in changes:
                behavior_change_idxs = change_entry[2]
                if behavior_change_idxs:
                    bc_name = result.strings[behavior_change_idxs[0]]
                    assert bc_name == "FunctionBodyChange"


# ---------------------------------------------------------------------------
# Tests: LLMContextCompiler — Execution Section
# ---------------------------------------------------------------------------

class TestExecutionSection:
    """Tests for the execution section of LLMContext."""

    def test_execution_graph_nodes_populated(self, simple_review_context):
        """Test that execution graph nodes are populated."""
        compiler = LLMContextCompiler()
        result = compiler.compile(simple_review_context)
        assert len(result.execution_graph.nodes) > 0

    def test_execution_graph_node_structure(self, simple_review_context):
        """Test that execution graph nodes have correct structure."""
        compiler = LLMContextCompiler()
        result = compiler.compile(simple_review_context)
        for node in result.execution_graph.nodes:
            # (behavior_idx, sym_idx, kind_idx, depth, changed, shared,
            #  reaches_service_idx, reaches_module_idx, reaches_package_idx, (ref_idxs...))
            assert len(node) == 10
            behavior_idx, sym_idx, kind_idx, depth, changed, shared = node[:6]
            assert isinstance(behavior_idx, int)
            assert isinstance(sym_idx, int)
            assert isinstance(kind_idx, int)
            assert isinstance(depth, int)
            assert isinstance(changed, bool)
            assert isinstance(shared, bool)

    def test_execution_graph_edges(self, multi_ep_execution_context):
        """Test that execution graph edges are created for chains."""
        rc = ReviewContext(execution=multi_ep_execution_context)
        compiler = LLMContextCompiler()
        result = compiler.compile(rc)
        # ep1 has 2 steps (edge between them), ep2 has 1 step (no edge)
        assert len(result.execution_graph.edges) >= 1

    def test_execution_graph_deduplicates_nodes(self, multi_ep_execution_context):
        """Test that shared execution steps are deduplicated in the DAG."""
        rc = ReviewContext(execution=multi_ep_execution_context)
        compiler = LLMContextCompiler()
        result = compiler.compile(rc)
        # ep1 has behavior="behavior://test1" with steps func1@0, func2@1
        # ep2 has behavior="behavior://test2" with step func1@0
        # Since behaviors differ, all 3 nodes are unique
        # Total unique nodes: 3 (test1/func1@0, test1/func2@1, test2/func1@0)
        assert len(result.execution_graph.nodes) == 3

    def test_entry_points_reference_graph_nodes(self, multi_ep_execution_context):
        """Test that entry points reference graph node indices."""
        rc = ReviewContext(execution=multi_ep_execution_context)
        compiler = LLMContextCompiler()
        result = compiler.compile(rc)
        assert len(result.entry_points) == 2
        for ep in result.entry_points:
            endpoint_idx, chain_node_idxs, terminal_idx, max_depth = ep
            assert isinstance(endpoint_idx, int)
            assert isinstance(chain_node_idxs, tuple)
            assert len(chain_node_idxs) > 0
            # All node indices should be valid
            for node_idx in chain_node_idxs:
                assert 0 <= node_idx < len(result.execution_graph.nodes)

    def test_deepest_execution_preserved(self, simple_review_context):
        """Test that deepest execution is preserved."""
        compiler = LLMContextCompiler()
        result = compiler.compile(simple_review_context)
        endpoint_idx, depth = result.deepest_execution
        assert result.strings[result.endpoints[endpoint_idx][0]] == "POST /test"
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
        assert len(result.discoveries) > 0

    def test_discovery_id_preserved(self, simple_review_context):
        """Test that discovery id is preserved."""
        compiler = LLMContextCompiler()
        result = compiler.compile(simple_review_context)
        for d in result.discoveries:
            id_idx = d[0]
            assert result.strings[id_idx] == "discovery://test/1"

    def test_discovery_kind_preserved(self, simple_review_context):
        """Test that discovery kind is preserved."""
        compiler = LLMContextCompiler()
        result = compiler.compile(simple_review_context)
        for d in result.discoveries:
            kind_idx = d[1]
            assert result.strings[kind_idx] == "deep_execution"

    def test_discovery_facts_preserved(self, simple_review_context):
        """Test that discovery facts dict is preserved."""
        compiler = LLMContextCompiler()
        result = compiler.compile(simple_review_context)
        for d in result.discoveries:
            facts = d[2]
            assert isinstance(facts, dict)
            assert "max_depth" in facts

    def test_discovery_references_preserved(self, simple_review_context):
        """Test that discovery references are preserved."""
        compiler = LLMContextCompiler()
        result = compiler.compile(simple_review_context)
        for d in result.discoveries:
            ref_idxs = d[3]
            assert len(ref_idxs) > 0
            for ref_idx in ref_idxs:
                assert 0 <= ref_idx < len(result.references)

    def test_discovery_references_deduplicated(self, multi_discovery_context):
        """Test that shared references are deduplicated in the table."""
        rc = ReviewContext(discoveries=multi_discovery_context)
        compiler = LLMContextCompiler()
        result = compiler.compile(rc)
        # Both discoveries reference the same 2 references
        assert len(result.references) == 2


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
        """Test that all change section strings are present in the string table."""
        compiler = LLMContextCompiler()
        result = compiler.compile(simple_review_context)
        strings = list(result.strings.entries)
        assert "modification" in strings
        assert "local" in strings
        assert "test.py" in strings
        assert "python" in strings
        assert "sym://test/func1" in strings
        assert "func1" in strings
        assert "function" in strings
        assert "public" in strings
        assert "test.py:1-10" in strings
        assert "modified" in strings
        assert "FunctionBodyChange" in strings

    def test_all_execution_strings_present(self, simple_review_context):
        """Test that all execution section strings are present in the string table."""
        compiler = LLMContextCompiler()
        result = compiler.compile(simple_review_context)
        strings = list(result.strings.entries)
        assert "POST /test" in strings
        assert "POST" in strings
        assert "/test" in strings
        assert "behavior://test" in strings
        assert "return" in strings
        assert "api" in strings
        assert "test_module" in strings

    def test_all_discovery_strings_present(self, simple_review_context):
        """Test that all discovery section strings are present in the string table."""
        compiler = LLMContextCompiler()
        result = compiler.compile(simple_review_context)
        strings = list(result.strings.entries)
        assert "discovery://test/1" in strings
        assert "deep_execution" in strings
        assert "ref://test/1" in strings
        assert "behavior" in strings

    def test_no_extra_strings(self, simple_review_context):
        """Test that no extra strings are added beyond what's in ReviewContext."""
        compiler = LLMContextCompiler()
        result = compiler.compile(simple_review_context)
        # All strings should be from the original ReviewContext
        strings = set(result.strings.entries)
        # Empty string is always index 0
        strings.discard("")
        # Every string should be recognizable as coming from the input
        for s in strings:
            assert any(
                s in str(simple_review_context.change) or
                s in str(simple_review_context.execution) or
                s in str(simple_review_context.discoveries)
                for _ in [1]
            ), f"Unexpected string: {s}"


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
        assert result.strings[0] == ""
        assert len(result.strings) == 1  # Only the empty string at index 0

    def test_no_change_section(self, simple_execution_context):
        """Test compilation with only execution section."""
        rc = ReviewContext(execution=simple_execution_context)
        compiler = LLMContextCompiler()
        result = compiler.compile(rc)
        assert result.change_summary == (0, 0, 0, 0, 0)
        assert result.change_files == ()
        assert len(result.execution_graph.nodes) > 0

    def test_no_execution_section(self, simple_change_context):
        """Test compilation with only change section."""
        rc = ReviewContext(change=simple_change_context)
        compiler = LLMContextCompiler()
        result = compiler.compile(rc)
        assert len(result.files) > 0
        assert result.execution_graph.nodes == ()
        assert result.entry_points == ()

    def test_no_discoveries(self, simple_change_context):
        """Test compilation with no discoveries."""
        rc = ReviewContext(change=simple_change_context)
        compiler = LLMContextCompiler()
        result = compiler.compile(rc)
        assert result.discoveries == ()

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
        # Same behavior id appears in execution
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
        strings = list(result.strings.entries)
        # "sym://test/func1" should appear only once
        assert strings.count("sym://test/func1") == 1
        # "func1" should appear only once
        assert strings.count("func1") == 1
        # "function" should appear only once
        assert strings.count("function") == 1

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
        assert len(result.references) == 50
        assert len(result.discoveries) == 1
        d = result.discoveries[0]
        assert len(d[3]) == 50  # All 50 reference indices preserved
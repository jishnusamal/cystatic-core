"""Tests for the ReviewContext Compiler — the public ABI of Factor.

Tests that the ReviewContextCompiler correctly transforms existing compiler outputs
into a stable engineering context without performing any discovery, graph traversal,
or recomputation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from engine.language.model import (
    RepositoryModel,
    Symbol,
    SymbolKind,
    SymbolVisibility,
    CallGraph,
    CallEdge,
    ReferenceGraph,
    EntryPoint as RepoEntryPoint,
    EntryPointKind,
)
from engine.change.model import (
    ChangeModel,
    ModifiedSymbol,
    ImportChange,
    EndpointChange,
)
from engine.change.model.changes import FunctionBodyChange
from engine.behavior.model import (
    Behavior,
    BehaviorKind,
    BehaviorModel,
    ExecutionGraph,
    ExecutionNode,
    ExecutionEdge,
    ExecutionUnit,
    ExecutionChain,
    EntryPoint,
    TerminalPoint,
    SharedExecution,
)
from engine.operational.model import OperationalChangeModel, EngineeringDiscoveryModel
from engine.discovery.model import (
    DiscoveryModel,
    Discovery as IRDiscovery,
    DiscoveryKind as IRDiscoveryKind,
    DiscoveryFact,
    DiscoveryReference,
)
from engine.review_context.compiler import ReviewContextCompiler
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


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TestHelper:
    """Helper for creating test fixtures."""

    @staticmethod
    def create_symbol(
        symbol_id: str,
        name: str,
        kind: SymbolKind,
        start_line: int = 1,
        end_line: int = 10,
        visibility: SymbolVisibility = SymbolVisibility.PUBLIC,
        language: str = "python",
        file: str = "test.py",
        properties: dict[str, Any] | None = None,
    ) -> Symbol:
        """Create a Symbol for testing."""
        return Symbol(
            id=symbol_id,
            name=name,
            kind=kind,
            language=language,
            file=file,
            range=(start_line, end_line),
            visibility=visibility,
            properties=properties or {},
        )

    @staticmethod
    def create_repository_model(
        symbols: list[Symbol],
        entry_points: list[RepoEntryPoint] | None = None,
        call_edges: list[CallEdge] | None = None,
    ) -> RepositoryModel:
        """Create a RepositoryModel for testing."""
        return RepositoryModel(
            symbols=frozenset(symbols),
            call_graph=CallGraph(edges=tuple(call_edges or [])),
            reference_graph=ReferenceGraph(edges=()),
            entry_points=tuple(entry_points or []),
        )

    @staticmethod
    def create_change_model(
        added_symbols: list[Symbol] | None = None,
        removed_symbols: list[Symbol] | None = None,
        modified_symbols: list[ModifiedSymbol] | None = None,
        changed_imports: list[ImportChange] | None = None,
        changed_endpoints: list[EndpointChange] | None = None,
        files_changed: int = 0,
    ) -> ChangeModel:
        """Create a ChangeModel for testing."""
        return ChangeModel(
            added_symbols=tuple(added_symbols or []),
            removed_symbols=tuple(removed_symbols or []),
            modified_symbols=tuple(modified_symbols or []),
            changed_imports=tuple(changed_imports or []),
            changed_endpoints=tuple(changed_endpoints or []),
            files_changed=files_changed,
        )

    @staticmethod
    def create_function_body_change() -> FunctionBodyChange:
        """Create a FunctionBodyChange for testing."""
        return FunctionBodyChange(
            old_body_hash="abc",
            new_body_hash="def",
        )

    @staticmethod
    def create_behavior_model(
        behaviors: list[Behavior] | None = None,
        execution_graphs: list[ExecutionGraph] | None = None,
        execution_chains: list[ExecutionChain] | None = None,
        entry_points: list[EntryPoint] | None = None,
        terminal_points: list[TerminalPoint] | None = None,
        shared_executions: list[SharedExecution] | None = None,
        reachable_units: list[ExecutionUnit] | None = None,
        execution_depth: int = 0,
    ) -> BehaviorModel:
        """Create a BehaviorModel for testing."""
        return BehaviorModel(
            behaviors=tuple(behaviors or []),
            execution_graphs=tuple(execution_graphs or []),
            execution_chains=tuple(execution_chains or []),
            entry_points=tuple(entry_points or []),
            terminal_points=tuple(terminal_points or []),
            shared_executions=tuple(shared_executions or []),
            reachable_units=tuple(reachable_units or []),
            execution_depth=execution_depth,
        )

    @staticmethod
    def create_discovery_ir(
        discoveries: list[IRDiscovery] | None = None,
    ) -> DiscoveryModel:
        """Create a DiscoveryModel for testing."""
        discoveries = discoveries or []
        return DiscoveryModel(
            discoveries=tuple(discoveries),
            metadata={
                "compiler_version": "1.0.0",
                "discovery_count": len(discoveries),
            },
        )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_symbols():
    """Create sample symbols for testing."""
    return [
        TestHelper.create_symbol(
            "python://test.py::func1",
            "func1",
            SymbolKind.FUNCTION,
        ),
        TestHelper.create_symbol(
            "python://test.py::func2",
            "func2",
            SymbolKind.FUNCTION,
            start_line=20,
            end_line=30,
        ),
        TestHelper.create_symbol(
            "python://test.py::MyClass",
            "MyClass",
            SymbolKind.CLASS,
            start_line=50,
            end_line=100,
        ),
    ]


@pytest.fixture
def sample_repository_model(sample_symbols):
    """Create a sample repository model for testing."""
    return TestHelper.create_repository_model(
        symbols=sample_symbols,
        entry_points=[
            RepoEntryPoint(
                kind=EntryPointKind.REST_ENDPOINT,
                route="POST /test",
                handler_id=sample_symbols[0].id,
            ),
        ],
    )


@pytest.fixture
def sample_change_model(sample_symbols):
    """Create a sample change model with various changes."""
    return TestHelper.create_change_model(
        added_symbols=[sample_symbols[1]],
        modified_symbols=[
            ModifiedSymbol(
                symbol=sample_symbols[0],
                changes=(
                    TestHelper.create_function_body_change(),
                ),
            ),
        ],
        changed_imports=[
            ImportChange(
                file="test.py",
                old_import=None,
                new_import="os",
                change_type="added",
            ),
        ],
        files_changed=2,
    )


@pytest.fixture
def sample_execution_units(sample_symbols):
    """Create sample execution units."""
    return [
        ExecutionUnit(
            id="unit://behavior://test/0",
            name="Process Request",
            symbol_id=sample_symbols[0].id,
            order=0,
        ),
        ExecutionUnit(
            id="unit://behavior://test/1",
            name="Validate Data",
            symbol_id=sample_symbols[1].id,
            order=1,
        ),
    ]


@pytest.fixture
def sample_entry_points():
    """Create sample entry points."""
    return [
        EntryPoint(
            id="ep://behavior://test",
            behavior_id="behavior://test",
            symbol_id="python://test.py::func1",
            kind="REST_ENDPOINT",
            route="POST /test",
        ),
    ]


@pytest.fixture
def sample_terminal_points():
    """Create sample terminal points."""
    return [
        TerminalPoint(
            id="tp://behavior://test/0",
            behavior_id="behavior://test",
            symbol_id="python://test.py::func2",
            kind="return",
        ),
    ]


@pytest.fixture
def sample_shared_executions(sample_symbols):
    """Create sample shared executions."""
    return [
        SharedExecution(
            id="shared://test/0",
            symbol_id=sample_symbols[0].id,
            used_by=("behavior://test", "behavior://other"),
        ),
    ]


@pytest.fixture
def sample_behavior_model(
    sample_symbols,
    sample_execution_units,
    sample_entry_points,
    sample_terminal_points,
    sample_shared_executions,
):
    """Create a sample behavior model with full execution context."""
    return TestHelper.create_behavior_model(
        behaviors=[
            Behavior(
                id="behavior://test",
                name="test_behavior",
                kind=BehaviorKind.REST_ENDPOINT,
                entry_point="POST /test",
                root_symbol_id=sample_symbols[0].id,
                changed_symbol_ids=(sample_symbols[1].id,),
            ),
        ],
        execution_chains=[
            ExecutionChain(
                id="chain://behavior://test",
                behavior_id="behavior://test",
                units=tuple(sample_execution_units),
            ),
        ],
        entry_points=sample_entry_points,
        terminal_points=sample_terminal_points,
        shared_executions=sample_shared_executions,
        reachable_units=sample_execution_units,
        execution_depth=2,
    )


@pytest.fixture
def sample_operational_model(
    sample_repository_model,
    sample_change_model,
    sample_behavior_model,
):
    """Create a sample operational change model for testing."""
    return OperationalChangeModel(
        repository=sample_repository_model,
        change=sample_change_model,
        behavior=sample_behavior_model,
    )


@pytest.fixture
def sample_discovery_model(
    sample_repository_model,
    sample_change_model,
    sample_behavior_model,
):
    """Create a sample EngineeringDiscoveryModel for testing."""
    return EngineeringDiscoveryModel(
        repository=sample_repository_model,
        change=sample_change_model,
        behavior=sample_behavior_model,
        execution_units=tuple(sample_behavior_model.reachable_units),
        execution_chains=sample_behavior_model.execution_chains,
        entry_points=sample_behavior_model.entry_points,
        terminal_points=sample_behavior_model.terminal_points,
        shared_executions=sample_behavior_model.shared_executions,
        reachable_units=sample_behavior_model.reachable_units,
        execution_depth=sample_behavior_model.execution_depth,
    )


@pytest.fixture
def sample_discovery_ir():
    """Create a sample DiscoveryModel for testing."""
    ref1 = DiscoveryReference(artifact_type="behavior", artifact_id="ref1", location="behavior://test")
    ref2 = DiscoveryReference(artifact_type="change", artifact_id="ref2", location="change://test")
    discoveries = [
        IRDiscovery(
            id="discovery://deep_execution/1",
            kind=IRDiscoveryKind.DEEP_EXECUTION,
            facts=DiscoveryFact(max_depth=2),
            references=(ref1,),
        ),
        IRDiscovery(
            id="discovery://shared_execution/1",
            kind=IRDiscoveryKind.SHARED_EXECUTION,
            facts=DiscoveryFact(shared_symbol_ids=("python://test.py::func1",), behavior_count=2),
            references=(ref2,),
        ),
        IRDiscovery(
            id="discovery://boundary/1",
            kind=IRDiscoveryKind.BOUNDARY_CROSSING,
            facts=DiscoveryFact(crossed_boundaries=("service_layer",), service_transitions=1),
            references=(ref1, ref2),
        ),
    ]
    return TestHelper.create_discovery_ir(discoveries)


# ---------------------------------------------------------------------------
# Tests: ReviewContextCompiler — Initialization
# ---------------------------------------------------------------------------

class TestReviewContextCompilerInit:
    """Tests for ReviewContextCompiler initialization."""

    def test_compiler_initialization(self):
        """Test that the compiler initializes without error."""
        compiler = ReviewContextCompiler()
        assert isinstance(compiler, ReviewContextCompiler)

    def test_compile_returns_review_context(self):
        """Test that compile returns a ReviewContext."""
        compiler = ReviewContextCompiler()
        result = compiler.compile()
        assert isinstance(result, ReviewContext)

    def test_compile_with_all_none_returns_empty(self):
        """Test that compiling with all None returns an empty ReviewContext."""
        compiler = ReviewContextCompiler()
        result = compiler.compile()
        assert isinstance(result.change, ChangeContext)
        assert isinstance(result.execution, ExecutionContext)
        assert result.discoveries == ()
        assert not hasattr(result, 'references')


# ---------------------------------------------------------------------------
# Tests: ReviewContextCompiler — ChangeContext — Summary
# ---------------------------------------------------------------------------

class TestChangeSummary:
    """Tests for ChangeSummary (the summary section)."""

    def test_summary_classification_addition(self, sample_symbols):
        """Test classification is 'addition' when only added symbols exist."""
        change_model = TestHelper.create_change_model(
            added_symbols=[sample_symbols[0]],
        )
        compiler = ReviewContextCompiler()
        result = compiler.compile(change_model=change_model)
        assert result.change.summary.classification == "addition"

    def test_summary_classification_modification(self, sample_symbols):
        """Test classification is 'modification' when only modified symbols exist."""
        change_model = TestHelper.create_change_model(
            modified_symbols=[
                ModifiedSymbol(symbol=sample_symbols[0], changes=()),
            ],
        )
        compiler = ReviewContextCompiler()
        result = compiler.compile(change_model=change_model)
        assert result.change.summary.classification == "modification"

    def test_summary_classification_removal(self, sample_symbols):
        """Test classification is 'removal' when only removed symbols exist."""
        change_model = TestHelper.create_change_model(
            removed_symbols=[sample_symbols[0]],
        )
        compiler = ReviewContextCompiler()
        result = compiler.compile(change_model=change_model)
        assert result.change.summary.classification == "removal"

    def test_summary_classification_mixed(self, sample_symbols):
        """Test classification is 'mixed' when both added and removed."""
        change_model = TestHelper.create_change_model(
            added_symbols=[sample_symbols[0]],
            removed_symbols=[sample_symbols[1]],
        )
        compiler = ReviewContextCompiler()
        result = compiler.compile(change_model=change_model)
        assert result.change.summary.classification == "mixed"

    def test_summary_scope_local(self, sample_symbols):
        """Test scope is 'local' when 1 file changed."""
        change_model = TestHelper.create_change_model(
            modified_symbols=[
                ModifiedSymbol(symbol=sample_symbols[0], changes=()),
            ],
            files_changed=1,
        )
        compiler = ReviewContextCompiler()
        result = compiler.compile(change_model=change_model)
        assert result.change.summary.scope == "local"

    def test_summary_scope_multi_file(self, sample_symbols):
        """Test scope is 'multi_file' when 2-5 files changed."""
        change_model = TestHelper.create_change_model(
            modified_symbols=[
                ModifiedSymbol(symbol=sample_symbols[0], changes=()),
            ],
            files_changed=3,
        )
        compiler = ReviewContextCompiler()
        result = compiler.compile(change_model=change_model)
        assert result.change.summary.scope == "multi_file"

    def test_summary_scope_wide(self, sample_symbols):
        """Test scope is 'wide' when >5 files changed."""
        change_model = TestHelper.create_change_model(
            modified_symbols=[
                ModifiedSymbol(symbol=sample_symbols[0], changes=()),
            ],
            files_changed=10,
        )
        compiler = ReviewContextCompiler()
        result = compiler.compile(change_model=change_model)
        assert result.change.summary.scope == "wide"

    def test_summary_counts(self, sample_change_model):
        """Test that summary counts are correct."""
        compiler = ReviewContextCompiler()
        result = compiler.compile(change_model=sample_change_model)
        assert result.change.summary.file_count > 0
        assert result.change.summary.symbol_count > 0


# ---------------------------------------------------------------------------
# Tests: ReviewContextCompiler — ChangeContext — Files
# ---------------------------------------------------------------------------

class TestFileChanges:
    """Tests for the hierarchical file-centered change structure."""

    def test_files_populated(self, sample_change_model):
        """Test that files are populated from change model."""
        compiler = ReviewContextCompiler()
        result = compiler.compile(change_model=sample_change_model)
        assert len(result.change.files) > 0

    def test_file_has_path(self, sample_change_model):
        """Test that each file has a path."""
        compiler = ReviewContextCompiler()
        result = compiler.compile(change_model=sample_change_model)
        for f in result.change.files:
            assert f.path != ""

    def test_file_has_change_type(self, sample_change_model):
        """Test that each file has a change type."""
        compiler = ReviewContextCompiler()
        result = compiler.compile(change_model=sample_change_model)
        for f in result.change.files:
            assert f.change_type in ("added", "removed", "modified", "mixed")

    def test_file_change_type_mixed(self, sample_symbols):
        """Test file change type is 'mixed' when file has added + removed symbols."""
        sym1 = TestHelper.create_symbol(
            "python://test.py::func1", "func1", SymbolKind.FUNCTION,
            file="test.py",
        )
        sym2 = TestHelper.create_symbol(
            "python://test.py::func2", "func2", SymbolKind.FUNCTION,
            file="test.py",
        )
        change_model = TestHelper.create_change_model(
            added_symbols=[sym1],
            removed_symbols=[sym2],
            files_changed=1,
        )
        compiler = ReviewContextCompiler()
        result = compiler.compile(change_model=change_model)
        assert len(result.change.files) == 1
        assert result.change.files[0].change_type == "mixed"

    def test_file_change_type_modified(self, sample_symbols):
        """Test file change type is 'modified' when only modified symbols."""
        change_model = TestHelper.create_change_model(
            modified_symbols=[
                ModifiedSymbol(symbol=sample_symbols[0], changes=()),
            ],
            files_changed=1,
        )
        compiler = ReviewContextCompiler()
        result = compiler.compile(change_model=change_model)
        assert len(result.change.files) == 1
        assert result.change.files[0].change_type == "modified"

    def test_file_change_type_added(self, sample_symbols):
        """Test file change type is 'added' when only added symbols."""
        change_model = TestHelper.create_change_model(
            added_symbols=[sample_symbols[0]],
            files_changed=1,
        )
        compiler = ReviewContextCompiler()
        result = compiler.compile(change_model=change_model)
        assert len(result.change.files) == 1
        assert result.change.files[0].change_type == "added"

    def test_file_has_language(self, sample_change_model):
        """Test that files have a language from symbol metadata."""
        compiler = ReviewContextCompiler()
        result = compiler.compile(change_model=sample_change_model)
        for f in result.change.files:
            assert f.language != ""

    def test_file_changes_populated(self, sample_change_model):
        """Test that file has changes (changed symbols)."""
        compiler = ReviewContextCompiler()
        result = compiler.compile(change_model=sample_change_model)
        for f in result.change.files:
            assert len(f.changes) > 0

    def test_change_symbol_ref(self, sample_change_model):
        """Test that each change has a symbol ref with metadata."""
        compiler = ReviewContextCompiler()
        result = compiler.compile(change_model=sample_change_model)
        for f in result.change.files:
            for c in f.changes:
                assert c.symbol.name != ""
                assert c.symbol.kind != ""
                assert c.symbol.visibility != ""
                assert c.symbol.location != ""

    def test_change_type_added(self, sample_change_model):
        """Test that added symbols have change_type 'added'."""
        compiler = ReviewContextCompiler()
        result = compiler.compile(change_model=sample_change_model)
        for f in result.change.files:
            for c in f.changes:
                if c.change_type == "added":
                    assert "func2" in c.symbol.name

    def test_change_type_modified(self, sample_change_model):
        """Test that modified symbols have change_type 'modified'."""
        compiler = ReviewContextCompiler()
        result = compiler.compile(change_model=sample_change_model)
        for f in result.change.files:
            for c in f.changes:
                if c.change_type == "modified":
                    assert "func1" in c.symbol.name

    def test_change_behavior_changes(self, sample_change_model):
        """Test that modified symbols carry behavior change types."""
        compiler = ReviewContextCompiler()
        result = compiler.compile(change_model=sample_change_model)
        for f in result.change.files:
            for c in f.changes:
                if c.change_type == "modified":
                    assert len(c.behavior_changes) > 0
                    assert "FunctionBodyChange" in c.behavior_changes

    def test_change_type_removed(self, sample_symbols):
        """Test that removed symbols have change_type 'removed'."""
        change_model = TestHelper.create_change_model(
            removed_symbols=[sample_symbols[0]],
        )
        compiler = ReviewContextCompiler()
        result = compiler.compile(change_model=change_model)
        for f in result.change.files:
            for c in f.changes:
                if c.change_type == "removed":
                    assert "func1" in c.symbol.name

    def test_no_flat_lists(self, sample_change_model):
        """Test that the old flat lists are gone."""
        compiler = ReviewContextCompiler()
        result = compiler.compile(change_model=sample_change_model)
        assert hasattr(result.change, 'summary')
        assert hasattr(result.change, 'files')
        assert not hasattr(result.change, 'changed_files')
        assert not hasattr(result.change, 'changed_symbols')
        assert not hasattr(result.change, 'changed_behaviors')

    def test_none_model(self):
        """Test that None change model returns empty ChangeContext."""
        compiler = ReviewContextCompiler()
        result = compiler.compile(change_model=None)
        assert result.change.summary.classification == ""
        assert result.change.summary.file_count == 0
        assert result.change.files == ()


# ---------------------------------------------------------------------------
# Tests: ReviewContextCompiler — ExecutionContext — Hierarchical Graph
# ---------------------------------------------------------------------------

class TestExecutionContextHierarchical:
    """Tests for the hierarchical execution graph structure."""

    def test_execution_context_with_behavior_model(self, sample_behavior_model):
        """Test that execution context is populated from behavior model."""
        compiler = ReviewContextCompiler()
        result = compiler.compile(behavior_model=sample_behavior_model)
        assert len(result.execution.entry_points) > 0

    def test_entry_point_has_endpoint(self, sample_behavior_model):
        """Test that entry point has an endpoint."""
        compiler = ReviewContextCompiler()
        result = compiler.compile(behavior_model=sample_behavior_model)
        for ep in result.execution.entry_points:
            assert ep.endpoint != ""

    def test_entry_point_has_method(self, sample_behavior_model):
        """Test that entry point has a method extracted from route."""
        compiler = ReviewContextCompiler()
        result = compiler.compile(behavior_model=sample_behavior_model)
        for ep in result.execution.entry_points:
            assert ep.method != ""

    def test_entry_point_method_from_route(self, sample_behavior_model):
        """Test that method is extracted from route (e.g., POST /test -> POST)."""
        compiler = ReviewContextCompiler()
        result = compiler.compile(behavior_model=sample_behavior_model)
        for ep in result.execution.entry_points:
            if "POST" in ep.path:
                assert ep.method == "POST"

    def test_entry_point_has_path(self, sample_behavior_model):
        """Test that entry point has a path."""
        compiler = ReviewContextCompiler()
        result = compiler.compile(behavior_model=sample_behavior_model)
        for ep in result.execution.entry_points:
            assert ep.path != ""

    def test_entry_point_execution_chain_populated(self, sample_behavior_model):
        """Test that execution chain has steps."""
        compiler = ReviewContextCompiler()
        result = compiler.compile(behavior_model=sample_behavior_model)
        for ep in result.execution.entry_points:
            assert len(ep.execution_chain) > 0

    def test_execution_step_has_behavior(self, sample_behavior_model):
        """Test that each execution step has a behavior identifier."""
        compiler = ReviewContextCompiler()
        result = compiler.compile(behavior_model=sample_behavior_model)
        for ep in result.execution.entry_points:
            for step in ep.execution_chain:
                assert step.behavior != ""

    def test_execution_step_has_symbol_id(self, sample_behavior_model):
        """Test that each execution step has a symbol reference."""
        compiler = ReviewContextCompiler()
        result = compiler.compile(behavior_model=sample_behavior_model)
        for ep in result.execution.entry_points:
            for step in ep.execution_chain:
                assert step.symbol.id != ""

    def test_execution_step_symbol_has_name(self, sample_behavior_model):
        """Test that symbol reference has a name."""
        compiler = ReviewContextCompiler()
        result = compiler.compile(behavior_model=sample_behavior_model)
        for ep in result.execution.entry_points:
            for step in ep.execution_chain:
                assert step.symbol.name != ""

    def test_execution_step_depth(self, sample_behavior_model):
        """Test that execution step preserves depth."""
        compiler = ReviewContextCompiler()
        result = compiler.compile(behavior_model=sample_behavior_model)
        for ep in result.execution.entry_points:
            for step in ep.execution_chain:
                assert isinstance(step.depth, int)

    def test_execution_step_changed_flag(self, sample_behavior_model):
        """Test that changed flag is present (boolean)."""
        compiler = ReviewContextCompiler()
        result = compiler.compile(behavior_model=sample_behavior_model)
        for ep in result.execution.entry_points:
            for step in ep.execution_chain:
                assert isinstance(step.changed, bool)

    def test_execution_step_shared_flag(self, sample_behavior_model):
        """Test that shared flag is present (boolean)."""
        compiler = ReviewContextCompiler()
        result = compiler.compile(behavior_model=sample_behavior_model)
        for ep in result.execution.entry_points:
            for step in ep.execution_chain:
                assert isinstance(step.shared, bool)

    def test_execution_step_reaches(self, sample_behavior_model):
        """Test that execution step has reached components."""
        compiler = ReviewContextCompiler()
        result = compiler.compile(behavior_model=sample_behavior_model)
        for ep in result.execution.entry_points:
            for step in ep.execution_chain:
                assert isinstance(step.reaches, ReachedComponents)

    def test_execution_step_reaches_service(self, sample_behavior_model):
        """Test that reached service is populated from behavior kind."""
        compiler = ReviewContextCompiler()
        result = compiler.compile(behavior_model=sample_behavior_model)
        for ep in result.execution.entry_points:
            for step in ep.execution_chain:
                assert step.reaches.service != ""

    def test_execution_step_reaches_module(self, sample_behavior_model):
        """Test that reached module is populated from behavior name."""
        compiler = ReviewContextCompiler()
        result = compiler.compile(behavior_model=sample_behavior_model)
        for ep in result.execution.entry_points:
            for step in ep.execution_chain:
                assert step.reaches.module != ""

    def test_execution_step_references(self, sample_behavior_model):
        """Test that execution step has references."""
        compiler = ReviewContextCompiler()
        result = compiler.compile(behavior_model=sample_behavior_model)
        for ep in result.execution.entry_points:
            for step in ep.execution_chain:
                assert isinstance(step.references, tuple)

    def test_entry_point_terminal(self, sample_behavior_model):
        """Test that entry point has terminal point kind."""
        compiler = ReviewContextCompiler()
        result = compiler.compile(behavior_model=sample_behavior_model)
        for ep in result.execution.entry_points:
            assert ep.terminal == "return"

    def test_entry_point_max_depth(self, sample_behavior_model):
        """Test that entry point has max depth."""
        compiler = ReviewContextCompiler()
        result = compiler.compile(behavior_model=sample_behavior_model)
        for ep in result.execution.entry_points:
            assert ep.max_depth >= 0

    def test_entry_point_references(self, sample_behavior_model):
        """Test that entry point has references."""
        compiler = ReviewContextCompiler()
        result = compiler.compile(behavior_model=sample_behavior_model)
        for ep in result.execution.entry_points:
            assert len(ep.references) > 0

    def test_deepest_execution_populated(self, sample_behavior_model):
        """Test that deepest execution is populated."""
        compiler = ReviewContextCompiler()
        result = compiler.compile(behavior_model=sample_behavior_model)
        assert result.execution.deepest_execution.entry_point != ""
        assert result.execution.deepest_execution.depth > 0

    def test_deepest_execution_depth_matches_max(self, sample_behavior_model):
        """Test that deepest execution depth matches max depth across entry points."""
        compiler = ReviewContextCompiler()
        result = compiler.compile(behavior_model=sample_behavior_model)
        max_depth = 0
        for ep in result.execution.entry_points:
            if ep.max_depth > max_depth:
                max_depth = ep.max_depth
        assert result.execution.deepest_execution.depth == max_depth

    def test_execution_order_preserved(self, sample_behavior_model):
        """Test that execution chain order matches the behavior graph."""
        compiler = ReviewContextCompiler()
        result = compiler.compile(behavior_model=sample_behavior_model)
        for ep in result.execution.entry_points:
            depths = [step.depth for step in ep.execution_chain]
            assert depths == sorted(depths)

    def test_changed_step_marked_correctly(self, sample_behavior_model, sample_change_model):
        """Test that changed symbols are marked correctly in execution steps."""
        compiler = ReviewContextCompiler()
        result = compiler.compile(
            behavior_model=sample_behavior_model,
            change_model=sample_change_model,
        )
        has_changed = any(
            step.changed
            for ep in result.execution.entry_points
            for step in ep.execution_chain
        )
        assert has_changed

    def test_shared_step_marked_correctly(self, sample_behavior_model):
        """Test that shared execution symbols are marked correctly."""
        compiler = ReviewContextCompiler()
        result = compiler.compile(behavior_model=sample_behavior_model)
        has_shared = any(
            step.shared
            for ep in result.execution.entry_points
            for step in ep.execution_chain
        )
        assert has_shared

    def test_no_flat_lists(self, sample_behavior_model):
        """Test that the old flat lists are gone from execution context."""
        compiler = ReviewContextCompiler()
        result = compiler.compile(behavior_model=sample_behavior_model)
        assert not hasattr(result.execution, 'execution_chains')
        assert not hasattr(result.execution, 'terminal_points')
        assert not hasattr(result.execution, 'reachable_units')
        assert not hasattr(result.execution, 'shared_execution')
        assert not hasattr(result.execution, 'max_execution_depth')

    def test_execution_context_none_models(self):
        """Test that None models return empty ExecutionContext."""
        compiler = ReviewContextCompiler()
        result = compiler.compile(behavior_model=None, discovery_model=None)
        assert result.execution.entry_points == ()
        assert result.execution.deepest_execution.entry_point == ""
        assert result.execution.deepest_execution.depth == 0


# ---------------------------------------------------------------------------
# Tests: ReviewContextCompiler — ValidationContext Selection
# ---------------------------------------------------------------------------

class TestValidationContextSelection:
    """Tests for ValidationContext selection (Pass 1)."""

# ---------------------------------------------------------------------------
# Tests: ReviewContextCompiler — Discovery Assembly (Pass 3)
# ---------------------------------------------------------------------------

class TestDiscoveryAssembly:
    """Tests for discovery assembly from DiscoveryModel."""

    def test_discoveries_populated(self, sample_discovery_ir):
        """Test that discoveries are populated from DiscoveryModel."""
        compiler = ReviewContextCompiler()
        result = compiler.compile(discovery_model=sample_discovery_ir)
        assert len(result.discoveries) > 0

    def test_discovery_kind_preserved(self, sample_discovery_ir):
        """Test that discovery kind is preserved."""
        compiler = ReviewContextCompiler()
        result = compiler.compile(discovery_model=sample_discovery_ir)
        kinds = {d.kind for d in result.discoveries}
        assert "deep_execution" in kinds
        assert "shared_execution" in kinds
        assert "boundary_crossing" in kinds

    def test_discovery_references_populated(self, sample_discovery_ir):
        """Test that discoveries can have references (when provided in source model)."""
        compiler = ReviewContextCompiler()
        result = compiler.compile(discovery_model=sample_discovery_ir)
        # References are optional in the new model - just verify the field exists
        for discovery in result.discoveries:
            assert isinstance(discovery.references, tuple)
            assert isinstance(discovery.reference_count, int)
            assert discovery.reference_count >= len(discovery.references)

    def test_discovery_reference_fields(self, sample_discovery_ir):
        """Test that reference fields are correctly populated."""
        compiler = ReviewContextCompiler()
        result = compiler.compile(discovery_model=sample_discovery_ir)
        for discovery in result.discoveries:
            for ref in discovery.references:
                assert ref.id != ""
                assert ref.kind != ""
                assert ref.compiler_artifact != ""

    def test_reference_count_preserved(self):
        """Test that reference_count preserves total count before truncation."""
        refs = tuple(
            DiscoveryReference(artifact_type="symbol", artifact_id=f"sym{i}", location=f"file{i}.py")
            for i in range(15)
        )
        discoveries = [
            IRDiscovery(
                id="discovery://many_refs/1",
                kind=IRDiscoveryKind.DEEP_EXECUTION,
                facts=DiscoveryFact(max_depth=2),
                references=refs,
            ),
        ]
        discovery_ir = TestHelper.create_discovery_ir(discoveries)
        compiler = ReviewContextCompiler()
        result = compiler.compile(discovery_model=discovery_ir)
        assert len(result.discoveries) == 1
        d = result.discoveries[0]
        assert d.reference_count == 15
        assert len(d.references) <= 10

    def test_reference_truncation_max_10(self):
        """Test that references are truncated to at most 10."""
        refs = tuple(
            DiscoveryReference(artifact_type="symbol", artifact_id=f"sym{i}", location=f"file{i}.py")
            for i in range(20)
        )
        discoveries = [
            IRDiscovery(
                id="discovery://truncated/1",
                kind=IRDiscoveryKind.SHARED_EXECUTION,
                facts=DiscoveryFact(shared_symbol_ids=("sym1",), behavior_count=2),
                references=refs,
            ),
        ]
        discovery_ir = TestHelper.create_discovery_ir(discoveries)
        compiler = ReviewContextCompiler()
        result = compiler.compile(discovery_model=discovery_ir)
        assert len(result.discoveries) == 1
        d = result.discoveries[0]
        assert d.reference_count == 20
        assert len(d.references) == 10

    def test_reference_ranking_prioritizes_changed(self):
        """Test that changed symbols are ranked first."""
        refs = (
            DiscoveryReference(artifact_type="symbol", artifact_id="sym1", location="impl.py"),
            DiscoveryReference(artifact_type="change", artifact_id="change1", location="change.py"),
            DiscoveryReference(artifact_type="behavior", artifact_id="ep1", location="endpoint.py"),
        )
        discoveries = [
            IRDiscovery(
                id="discovery://ranked/1",
                kind=IRDiscoveryKind.DEEP_EXECUTION,
                facts=DiscoveryFact(max_depth=2),
                references=refs,
            ),
        ]
        discovery_ir = TestHelper.create_discovery_ir(discoveries)
        compiler = ReviewContextCompiler()
        result = compiler.compile(discovery_model=discovery_ir)
        assert len(result.discoveries) == 1
        d = result.discoveries[0]
        assert d.reference_count == 3
        assert len(d.references) == 3
        # Changed should be first
        assert d.references[0].kind == "change"
        # Behavior/entry point should be second
        assert d.references[1].kind == "behavior"
        # Symbol should be last
        assert d.references[2].kind == "symbol"

    def test_reference_deduplication_before_ranking(self):
        """Test that duplicate references are removed before ranking."""
        refs = (
            DiscoveryReference(artifact_type="change", artifact_id="change1", location="change.py"),
            DiscoveryReference(artifact_type="change", artifact_id="change1", location="change.py"),  # Duplicate
            DiscoveryReference(artifact_type="behavior", artifact_id="ep1", location="endpoint.py"),
        )
        discoveries = [
            IRDiscovery(
                id="discovery://dedup/1",
                kind=IRDiscoveryKind.DEEP_EXECUTION,
                facts=DiscoveryFact(max_depth=2),
                references=refs,
            ),
        ]
        discovery_ir = TestHelper.create_discovery_ir(discoveries)
        compiler = ReviewContextCompiler()
        result = compiler.compile(discovery_model=discovery_ir)
        assert len(result.discoveries) == 1
        d = result.discoveries[0]
        assert d.reference_count == 3
        assert len(d.references) == 2  # Deduplicated

    def test_discovery_no_importance_scores(self, sample_discovery_ir):
        """Test that importance scores are NOT present."""
        compiler = ReviewContextCompiler()
        result = compiler.compile(discovery_model=sample_discovery_ir)
        for discovery in result.discoveries:
            assert not hasattr(discovery, 'importance')

    def test_discovery_no_ranking_vectors(self, sample_discovery_ir):
        """Test that ranking vectors are NOT present."""
        compiler = ReviewContextCompiler()
        result = compiler.compile(discovery_model=sample_discovery_ir)
        for discovery in result.discoveries:
            assert not hasattr(discovery, 'ranking_vector')

    def test_discovery_no_support_metrics(self, sample_discovery_ir):
        """Test that support metrics are NOT present."""
        compiler = ReviewContextCompiler()
        result = compiler.compile(discovery_model=sample_discovery_ir)
        for discovery in result.discoveries:
            assert not hasattr(discovery, 'support')

    def test_discovery_no_metadata(self, sample_discovery_ir):
        """Test that discovery metadata is NOT present (metadata is on model, not discovery)."""
        compiler = ReviewContextCompiler()
        result = compiler.compile(discovery_model=sample_discovery_ir)
        # Metadata exists on DiscoveryModel, not on individual Discovery objects
        for discovery in result.discoveries:
            assert not hasattr(discovery, 'metadata')

    def test_discoveries_empty_when_no_ir(self):
        """Test that no DiscoveryModel returns empty discoveries."""
        compiler = ReviewContextCompiler()
        result = compiler.compile(discovery_model=None)
        assert result.discoveries == ()


# ---------------------------------------------------------------------------
# Tests: ReviewContextCompiler — Reference Assembly (Pass 4)
# ---------------------------------------------------------------------------

class TestReferenceAssembly:
    """Tests for reference assembly from discoveries."""

    def test_references_populated(self, sample_discovery_ir):
        """Test that references are NOT collected at top level (removed)."""
        compiler = ReviewContextCompiler()
        result = compiler.compile(discovery_model=sample_discovery_ir)
        # Top-level references were removed - each section owns its own
        assert not hasattr(result, 'references')

    def test_references_deduplicated(self):
        """Test that references are deduplicated by id within each discovery."""
        ref1 = DiscoveryReference(artifact_type="behavior", artifact_id="ref1", location="test.py")
        ref2 = DiscoveryReference(artifact_type="change", artifact_id="ref2", location="test2.py")
        discoveries = [
            IRDiscovery(
                id="discovery://a/1",
                kind=IRDiscoveryKind.DEEP_EXECUTION,
                facts=DiscoveryFact(max_depth=2),
                references=(ref1, ref2),
            ),
            IRDiscovery(
                id="discovery://b/1",
                kind=IRDiscoveryKind.SHARED_EXECUTION,
                facts=DiscoveryFact(shared_symbol_ids=("sym1",), behavior_count=2),
                references=(ref1, ref2),  # Same references
            ),
        ]
        discovery_ir = TestHelper.create_discovery_ir(discoveries)
        compiler = ReviewContextCompiler()
        result = compiler.compile(discovery_model=discovery_ir)
        # Each discovery owns its own references - no top-level collection
        assert not hasattr(result, 'references')
        # Verify references are within discoveries
        for d in result.discoveries:
            assert len(d.references) > 0

    def test_references_traceable(self, sample_discovery_ir):
        """Test that references within discoveries are traceable to compiler artifacts."""
        compiler = ReviewContextCompiler()
        result = compiler.compile(discovery_model=sample_discovery_ir)
        for d in result.discoveries:
            for ref in d.references:
                assert ref.compiler_artifact != ""
                assert ref.location != ""

    def test_references_empty_when_no_discoveries(self):
        """Test that no discoveries returns no top-level references field."""
        compiler = ReviewContextCompiler()
        result = compiler.compile(discovery_model=None)
        assert not hasattr(result, 'references')


# ---------------------------------------------------------------------------
# Tests: ReviewContextCompiler — Full Compilation
# ---------------------------------------------------------------------------

class TestFullCompilation:
    """Tests for full ReviewContext compilation."""

    def test_full_compile_returns_review_context(
        self,
        sample_change_model,
        sample_behavior_model,
        sample_operational_model,
        sample_discovery_model,
        sample_discovery_ir,
    ):
        """Test that full compilation returns a complete ReviewContext."""
        compiler = ReviewContextCompiler()
        result = compiler.compile(
            change_model=sample_change_model,
            behavior_model=sample_behavior_model,
            operational_model=sample_operational_model,
            discovery_model=sample_discovery_ir,
        )
        assert isinstance(result, ReviewContext)
        assert isinstance(result.change, ChangeContext)
        assert isinstance(result.execution, ExecutionContext)
        assert isinstance(result.discoveries, tuple)
        assert not hasattr(result, 'references')

    def test_full_compile_all_sections_populated(
        self,
        sample_change_model,
        sample_behavior_model,
        sample_operational_model,
        sample_discovery_model,
        sample_discovery_ir,
    ):
        """Test that all sections are populated in full compilation."""
        compiler = ReviewContextCompiler()
        result = compiler.compile(
            change_model=sample_change_model,
            behavior_model=sample_behavior_model,
            operational_model=sample_operational_model,
            discovery_model=sample_discovery_ir,
        )
        assert result.change.summary.file_count > 0
        assert len(result.change.files) > 0
        assert len(result.execution.entry_points) > 0
        assert len(result.discoveries) > 0
        # Each discovery owns its own references
        for d in result.discoveries:
            assert len(d.references) > 0

    def test_deterministic_output(
        self,
        sample_change_model,
        sample_behavior_model,
        sample_operational_model,
        sample_discovery_model,
        sample_discovery_ir,
    ):
        """Test that compilation is deterministic."""
        compiler = ReviewContextCompiler()
        result1 = compiler.compile(
            change_model=sample_change_model,
            behavior_model=sample_behavior_model,
            operational_model=sample_operational_model,
            discovery_model=sample_discovery_ir,
        )
        result2 = compiler.compile(
            change_model=sample_change_model,
            behavior_model=sample_behavior_model,
            operational_model=sample_operational_model,
            discovery_model=sample_discovery_ir,
        )
        assert result1 == result2

    def test_immutable_output(
        self,
        sample_change_model,
        sample_behavior_model,
        sample_operational_model,
        sample_discovery_model,
        sample_discovery_ir,
    ):
        """Test that ReviewContext is immutable."""
        compiler = ReviewContextCompiler()
        result = compiler.compile(
            change_model=sample_change_model,
            behavior_model=sample_behavior_model,
            operational_model=sample_operational_model,
            discovery_model=sample_discovery_ir,
        )
        with pytest.raises(AttributeError):
            result.change = ChangeContext()  # type: ignore

    def test_no_impact_section(self, sample_behavior_model):
        """Test that ImpactContext is no longer part of ReviewContext."""
        compiler = ReviewContextCompiler()
        result = compiler.compile(behavior_model=sample_behavior_model)
        assert not hasattr(result, 'impact')

    def test_no_compiler_metrics_in_execution(self, sample_behavior_model):
        """Test that compiler metrics (fan_in, fan_out) are not in execution."""
        compiler = ReviewContextCompiler()
        result = compiler.compile(behavior_model=sample_behavior_model)
        assert not hasattr(result.execution, 'fan_in')
        assert not hasattr(result.execution, 'fan_out')


# ---------------------------------------------------------------------------
# Tests: ReviewContextCompiler — Edge Cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Tests for edge cases in ReviewContext compilation."""

    def test_empty_change_model(self):
        """Test with an empty change model."""
        change_model = TestHelper.create_change_model()
        compiler = ReviewContextCompiler()
        result = compiler.compile(change_model=change_model)
        assert result.change.files == ()
        assert result.change.summary.classification == "modification"

    def test_empty_behavior_model(self):
        """Test with an empty behavior model."""
        behavior_model = TestHelper.create_behavior_model()
        compiler = ReviewContextCompiler()
        result = compiler.compile(behavior_model=behavior_model)
        assert result.execution.entry_points == ()
        assert result.execution.deepest_execution.depth == 0

    def test_empty_discovery_ir(self):
        """Test with an empty DiscoveryModel."""
        discovery_ir = TestHelper.create_discovery_ir([])
        compiler = ReviewContextCompiler()
        result = compiler.compile(discovery_model=discovery_ir)
        assert result.discoveries == ()
        assert not hasattr(result, 'references')

    def test_partial_models_change_only(self, sample_change_model):
        """Test with only change model provided."""
        compiler = ReviewContextCompiler()
        result = compiler.compile(change_model=sample_change_model)
        assert len(result.change.files) > 0
        assert result.execution.entry_points == ()
        assert result.discoveries == ()

    def test_partial_models_behavior_only(self, sample_behavior_model):
        """Test with only behavior model provided."""
        compiler = ReviewContextCompiler()
        result = compiler.compile(behavior_model=sample_behavior_model)
        assert len(result.execution.entry_points) > 0
        assert result.change.summary.file_count == 0
        assert result.discoveries == ()

    def test_partial_models_discovery_only(self, sample_discovery_ir):
        """Test with only DiscoveryModel provided."""
        compiler = ReviewContextCompiler()
        result = compiler.compile(discovery_model=sample_discovery_ir)
        assert len(result.discoveries) > 0
        assert result.change.summary.file_count == 0
        assert result.execution.entry_points == ()

    def test_discovery_without_evidence(self):
        """Test that a discovery without references still appears."""
        discoveries = [
            IRDiscovery(
                id="discovery://no_evidence/1",
                kind=IRDiscoveryKind.DEEP_EXECUTION,
                facts=DiscoveryFact(max_depth=2),
                references=(),
            ),
        ]
        discovery_ir = TestHelper.create_discovery_ir(discoveries)
        compiler = ReviewContextCompiler()
        result = compiler.compile(discovery_model=discovery_ir)
        assert len(result.discoveries) == 1
        assert result.discoveries[0].references == ()
        assert result.discoveries[0].reference_count == 0
        assert not hasattr(result, 'references')


# ---------------------------------------------------------------------------
# Tests: ReviewContext Model — Immutability
# ---------------------------------------------------------------------------

class TestReviewContextModel:
    """Tests for ReviewContext model immutability and structure."""

    def test_review_context_immutable(self):
        """Test that ReviewContext is frozen."""
        ctx = ReviewContext()
        with pytest.raises(AttributeError):
            ctx.change = ChangeContext()  # type: ignore

    def test_change_summary_immutable(self):
        """Test that ChangeSummary is frozen."""
        s = ChangeSummary()
        with pytest.raises(AttributeError):
            s.classification = "new"  # type: ignore

    def test_file_change_immutable(self):
        """Test that FileChange is frozen."""
        f = FileChange()
        with pytest.raises(AttributeError):
            f.path = "new.py"  # type: ignore

    def test_change_immutable(self):
        """Test that Change is frozen."""
        c = Change()
        with pytest.raises(AttributeError):
            c.change_type = "new"  # type: ignore

    def test_symbol_ref_immutable(self):
        """Test that SymbolRef is frozen."""
        s = SymbolRef()
        with pytest.raises(AttributeError):
            s.name = "new"  # type: ignore

    def test_execution_context_immutable(self):
        """Test that ExecutionContext is frozen."""
        ctx = ExecutionContext()
        with pytest.raises(AttributeError):
            ctx.entry_points = ("ep1",)  # type: ignore

    def test_entry_point_execution_immutable(self):
        """Test that EntryPointExecution is frozen."""
        ep = EntryPointExecution()
        with pytest.raises(AttributeError):
            ep.endpoint = "new"  # type: ignore

    def test_execution_step_immutable(self):
        """Test that ExecutionStep is frozen."""
        step = ExecutionStep()
        with pytest.raises(AttributeError):
            step.behavior = "new"  # type: ignore

    def test_symbol_reference_immutable(self):
        """Test that SymbolReference is frozen."""
        sr = SymbolReference()
        with pytest.raises(AttributeError):
            sr.name = "new"  # type: ignore

    def test_reached_components_immutable(self):
        """Test that ReachedComponents is frozen."""
        rc = ReachedComponents()
        with pytest.raises(AttributeError):
            rc.service = "new"  # type: ignore

    def test_deepest_execution_immutable(self):
        """Test that DeepestExecution is frozen."""
        de = DeepestExecution()
        with pytest.raises(AttributeError):
            de.depth = 10  # type: ignore

    def test_discovery_immutable(self):
        """Test that Discovery is frozen."""
        d = Discovery(id="d1", kind="execution_depth", statement="test")
        with pytest.raises(AttributeError):
            d.statement = "new"  # type: ignore

    def test_reference_immutable(self):
        """Test that Reference is frozen."""
        r = Reference(id="r1", kind="behavior", location="test.py")
        with pytest.raises(AttributeError):
            r.location = "new.py"  # type: ignore

    def test_review_context_defaults(self):
        """Test that ReviewContext has sensible defaults."""
        ctx = ReviewContext()
        assert ctx.change.summary.file_count == 0
        assert ctx.change.files == ()
        assert ctx.execution.entry_points == ()
        assert ctx.execution.deepest_execution.entry_point == ""
        assert ctx.execution.deepest_execution.depth == 0
        assert ctx.discoveries == ()
        assert not hasattr(ctx, 'references')

    def test_review_context_no_impact(self):
        """Test that ReviewContext no longer has an impact section."""
        ctx = ReviewContext()
        assert not hasattr(ctx, 'impact')

    def test_review_context_all_fields_present(self):
        """Test that ReviewContext has all required fields."""
        ctx = ReviewContext()
        assert hasattr(ctx, 'change')
        assert hasattr(ctx, 'execution')
        assert hasattr(ctx, 'discoveries')
        assert not hasattr(ctx, 'references')  # Removed - each section owns its own

    def test_discovery_no_presentation_fields(self):
        """Test that Discovery has no presentation fields."""
        d = Discovery(id="d1", kind="execution_depth", statement="test")
        assert not hasattr(d, 'title')
        assert not hasattr(d, 'summary')
        assert not hasattr(d, 'description')
        assert not hasattr(d, 'importance')
        assert not hasattr(d, 'ranking_vector')
        assert not hasattr(d, 'narrative_position')
        assert not hasattr(d, 'visual_semantic')

    def test_reference_no_presentation_fields(self):
        """Test that Reference has no presentation fields."""
        r = Reference(id="r1", kind="behavior", location="test.py")
        assert not hasattr(r, 'title')
        assert not hasattr(r, 'description')
        assert not hasattr(r, 'format')
        assert not hasattr(r, 'style')
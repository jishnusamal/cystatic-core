"""Tests for the ReviewContext Compiler — the public ABI of Factor.

Tests that the ReviewContextCompiler correctly transforms existing compiler outputs
into a stable engineering context without performing any discovery, graph traversal,
or recomputation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from language_adapters.model import (
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
from change.model import (
    ChangeModel,
    ModifiedSymbol,
    ImportChange,
    EndpointChange,
)
from change.model.changes import FunctionBodyChange
from behavior.model import (
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
from operational.model import OperationalChangeModel, EngineeringDiscoveryModel
from operational.discovery.model import (
    DiscoveryIR,
    Discovery as IRDiscovery,
    DiscoveryKind as IRDiscoveryKind,
    DiscoveryMetadata,
    DiscoverySummary,
    DiscoveryEvidence,
    DiscoverySupport,
)
from review_context.compiler import ReviewContextCompiler
from review_context.model import (
    ReviewContext,
    ChangeContext,
    ChangeSummary,
    FileChange,
    Change,
    SymbolRef,
    ExecutionContext,
    ImpactContext,
    StateContext,
    IntegrationContext,
    ValidationContext,
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
    ) -> DiscoveryIR:
        """Create a DiscoveryIR for testing."""
        discoveries = discoveries or []
        return DiscoveryIR(
            metadata=DiscoveryMetadata(
                compiler_version="1.0.0",
                compiled_at="2024-01-01T00:00:00Z",
                discovery_count=len(discoveries),
                evidence_count=sum(len(d.evidence) for d in discoveries),
                pass_count=5,
            ),
            discoveries=tuple(discoveries),
            summary=DiscoverySummary(
                total_discoveries=len(discoveries),
            ),
            evidence_index={
                d.id: d.evidence for d in discoveries
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
    """Create a sample DiscoveryIR for testing."""
    discoveries = [
        IRDiscovery(
            id="discovery://execution_depth/1",
            kind=IRDiscoveryKind.EXECUTION_DEPTH,
            statement="Maximum execution depth is 2 across all behaviors",
            importance=0.8,
            support=DiscoverySupport(execution_reach=2),
            evidence=(
                DiscoveryEvidence(
                    source="behavior",
                    source_id="depth://behavior://test",
                    description="Execution depth measurement",
                    evidence_ref="behavior://test/depth",
                ),
            ),
        ),
        IRDiscovery(
            id="discovery://shared_execution/1",
            kind=IRDiscoveryKind.SHARED_EXECUTION,
            statement="Symbol func1 is shared across 2 behaviors",
            importance=0.7,
            support=DiscoverySupport(shared_by_count=2),
            evidence=(
                DiscoveryEvidence(
                    source="behavior",
                    source_id="shared://test/0",
                    description="Shared execution detected",
                    evidence_ref="behavior://test/shared",
                ),
            ),
        ),
        IRDiscovery(
            id="discovery://boundary/1",
            kind=IRDiscoveryKind.BOUNDARY_INVARIANT,
            statement="Boundary crossing detected between service layers",
            importance=0.9,
            support=DiscoverySupport(boundary_crossings=1),
            evidence=(
                DiscoveryEvidence(
                    source="behavior",
                    source_id="boundary://test/0",
                    description="Cross-boundary call detected",
                    evidence_ref="behavior://test/boundary",
                ),
            ),
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
        assert isinstance(result.impact, ImpactContext)
        assert isinstance(result.state, StateContext)
        assert isinstance(result.integration, IntegrationContext)
        assert isinstance(result.validation, ValidationContext)
        assert result.discoveries == ()
        assert result.references == ()


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
        # Both symbols in same file
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
        # ChangeContext should have summary and files, not flat lists
        assert hasattr(result.change, 'summary')
        assert hasattr(result.change, 'files')
        # Verify no old-style flat list attributes
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
# Tests: ReviewContextCompiler — ExecutionContext Selection
# ---------------------------------------------------------------------------

class TestExecutionContextSelection:
    """Tests for ExecutionContext selection (Pass 1)."""

    def test_execution_context_with_behavior_model(self, sample_behavior_model):
        """Test that execution context is populated from behavior model."""
        compiler = ReviewContextCompiler()
        result = compiler.compile(behavior_model=sample_behavior_model)
        assert len(result.execution.entry_points) > 0
        assert "POST /test" in result.execution.entry_points
        assert result.execution.max_execution_depth == 2

    def test_execution_context_entry_points(self, sample_behavior_model):
        """Test that entry points are extracted."""
        compiler = ReviewContextCompiler()
        result = compiler.compile(behavior_model=sample_behavior_model)
        assert "POST /test" in result.execution.entry_points

    def test_execution_context_execution_chains(self, sample_behavior_model):
        """Test that execution chains are extracted."""
        compiler = ReviewContextCompiler()
        result = compiler.compile(behavior_model=sample_behavior_model)
        assert len(result.execution.execution_chains) > 0

    def test_execution_context_terminal_points(self, sample_behavior_model):
        """Test that terminal points are extracted."""
        compiler = ReviewContextCompiler()
        result = compiler.compile(behavior_model=sample_behavior_model)
        assert len(result.execution.terminal_points) > 0

    def test_execution_context_reachable_units(self, sample_behavior_model):
        """Test that reachable units are extracted."""
        compiler = ReviewContextCompiler()
        result = compiler.compile(behavior_model=sample_behavior_model)
        assert len(result.execution.reachable_units) > 0

    def test_execution_context_shared_execution(self, sample_behavior_model):
        """Test that shared executions are extracted."""
        compiler = ReviewContextCompiler()
        result = compiler.compile(behavior_model=sample_behavior_model)
        assert len(result.execution.shared_execution) > 0

    def test_execution_context_max_depth(self, sample_behavior_model):
        """Test that max execution depth is extracted."""
        compiler = ReviewContextCompiler()
        result = compiler.compile(behavior_model=sample_behavior_model)
        assert result.execution.max_execution_depth == 2

    def test_execution_context_none_models(self):
        """Test that None models return empty ExecutionContext."""
        compiler = ReviewContextCompiler()
        result = compiler.compile(behavior_model=None, discovery_model=None)
        assert result.execution.entry_points == ()
        assert result.execution.max_execution_depth == 0


# ---------------------------------------------------------------------------
# Tests: ReviewContextCompiler — ImpactContext Selection
# ---------------------------------------------------------------------------

class TestImpactContextSelection:
    """Tests for ImpactContext selection (Pass 1)."""

    def test_impact_context_with_behavior_model(self, sample_behavior_model):
        """Test that impact context is populated from behavior model."""
        compiler = ReviewContextCompiler()
        result = compiler.compile(behavior_model=sample_behavior_model)
        assert len(result.impact.modules) > 0
        assert len(result.impact.services) > 0

    def test_impact_context_fan_in(self, sample_behavior_model):
        """Test that fan-in is extracted from entry points."""
        compiler = ReviewContextCompiler()
        result = compiler.compile(behavior_model=sample_behavior_model)
        assert result.impact.fan_in > 0

    def test_impact_context_fan_out(self, sample_behavior_model):
        """Test that fan-out is extracted from reachable units."""
        compiler = ReviewContextCompiler()
        result = compiler.compile(behavior_model=sample_behavior_model)
        assert result.impact.fan_out > 0

    def test_impact_context_none_models(self):
        """Test that None models return empty ImpactContext."""
        compiler = ReviewContextCompiler()
        result = compiler.compile(behavior_model=None, discovery_model=None)
        assert result.impact.services == ()
        assert result.impact.fan_in == 0
        assert result.impact.fan_out == 0


# ---------------------------------------------------------------------------
# Tests: ReviewContextCompiler — StateContext Selection
# ---------------------------------------------------------------------------

class TestStateContextSelection:
    """Tests for StateContext selection (Pass 1)."""

    def test_state_context_none_models(self):
        """Test that None models return empty StateContext."""
        compiler = ReviewContextCompiler()
        result = compiler.compile(operational_model=None, discovery_model=None)
        assert result.state.models == ()
        assert result.state.tables == ()

    def test_state_context_empty_operational(self, sample_behavior_model):
        """Test that operational model without data returns empty state."""
        operational = OperationalChangeModel(
            repository=TestHelper.create_repository_model(symbols=[]),
            change=TestHelper.create_change_model(),
            behavior=sample_behavior_model,
        )
        compiler = ReviewContextCompiler()
        result = compiler.compile(operational_model=operational)
        assert result.state.models == ()


# ---------------------------------------------------------------------------
# Tests: ReviewContextCompiler — IntegrationContext Selection
# ---------------------------------------------------------------------------

class TestIntegrationContextSelection:
    """Tests for IntegrationContext selection (Pass 1)."""

    def test_integration_context_none_models(self):
        """Test that None models return empty IntegrationContext."""
        compiler = ReviewContextCompiler()
        result = compiler.compile(operational_model=None, discovery_model=None)
        assert result.integration.rest == ()
        assert result.integration.events == ()

    def test_integration_context_empty_operational(self, sample_behavior_model):
        """Test that operational model without API/events returns empty."""
        operational = OperationalChangeModel(
            repository=TestHelper.create_repository_model(symbols=[]),
            change=TestHelper.create_change_model(),
            behavior=sample_behavior_model,
        )
        compiler = ReviewContextCompiler()
        result = compiler.compile(operational_model=operational)
        assert result.integration.rest == ()


# ---------------------------------------------------------------------------
# Tests: ReviewContextCompiler — ValidationContext Selection
# ---------------------------------------------------------------------------

class TestValidationContextSelection:
    """Tests for ValidationContext selection (Pass 1)."""

    def test_validation_context_none_models(self):
        """Test that None models return empty ValidationContext."""
        compiler = ReviewContextCompiler()
        result = compiler.compile(operational_model=None, discovery_model=None)
        assert result.validation.unit_tests == ()
        assert result.validation.integration_tests == ()

    def test_validation_context_empty_operational(self, sample_behavior_model):
        """Test that operational model without validation returns empty."""
        operational = OperationalChangeModel(
            repository=TestHelper.create_repository_model(symbols=[]),
            change=TestHelper.create_change_model(),
            behavior=sample_behavior_model,
        )
        compiler = ReviewContextCompiler()
        result = compiler.compile(operational_model=operational)
        assert result.validation.unit_tests == ()


# ---------------------------------------------------------------------------
# Tests: ReviewContextCompiler — Discovery Assembly (Pass 3)
# ---------------------------------------------------------------------------

class TestDiscoveryAssembly:
    """Tests for discovery assembly from DiscoveryIR."""

    def test_discoveries_populated(self, sample_discovery_ir):
        """Test that discoveries are populated from DiscoveryIR."""
        compiler = ReviewContextCompiler()
        result = compiler.compile(discovery_ir=sample_discovery_ir)
        assert len(result.discoveries) > 0

    def test_discovery_kind_preserved(self, sample_discovery_ir):
        """Test that discovery kind is preserved."""
        compiler = ReviewContextCompiler()
        result = compiler.compile(discovery_ir=sample_discovery_ir)
        kinds = {d.kind for d in result.discoveries}
        assert "execution_depth" in kinds
        assert "shared_execution" in kinds
        assert "boundary_invariant" in kinds

    def test_discovery_statement_preserved(self, sample_discovery_ir):
        """Test that discovery statement is preserved."""
        compiler = ReviewContextCompiler()
        result = compiler.compile(discovery_ir=sample_discovery_ir)
        statements = {d.statement for d in result.discoveries}
        assert "Maximum execution depth is 2 across all behaviors" in statements

    def test_discovery_references_populated(self, sample_discovery_ir):
        """Test that discoveries have references."""
        compiler = ReviewContextCompiler()
        result = compiler.compile(discovery_ir=sample_discovery_ir)
        for discovery in result.discoveries:
            assert len(discovery.references) > 0

    def test_discovery_reference_fields(self, sample_discovery_ir):
        """Test that reference fields are correctly populated."""
        compiler = ReviewContextCompiler()
        result = compiler.compile(discovery_ir=sample_discovery_ir)
        for discovery in result.discoveries:
            for ref in discovery.references:
                assert ref.id != ""
                assert ref.kind != ""
                assert ref.compiler_artifact != ""

    def test_discovery_no_importance_scores(self, sample_discovery_ir):
        """Test that importance scores are NOT present."""
        compiler = ReviewContextCompiler()
        result = compiler.compile(discovery_ir=sample_discovery_ir)
        for discovery in result.discoveries:
            assert not hasattr(discovery, 'importance')

    def test_discovery_no_ranking_vectors(self, sample_discovery_ir):
        """Test that ranking vectors are NOT present."""
        compiler = ReviewContextCompiler()
        result = compiler.compile(discovery_ir=sample_discovery_ir)
        for discovery in result.discoveries:
            assert not hasattr(discovery, 'ranking_vector')

    def test_discovery_no_support_metrics(self, sample_discovery_ir):
        """Test that support metrics are NOT present."""
        compiler = ReviewContextCompiler()
        result = compiler.compile(discovery_ir=sample_discovery_ir)
        for discovery in result.discoveries:
            assert not hasattr(discovery, 'support')

    def test_discovery_no_metadata(self, sample_discovery_ir):
        """Test that compiler metadata is NOT present."""
        compiler = ReviewContextCompiler()
        result = compiler.compile(discovery_ir=sample_discovery_ir)
        for discovery in result.discoveries:
            assert not hasattr(discovery, 'metadata')

    def test_discoveries_empty_when_no_ir(self):
        """Test that no DiscoveryIR returns empty discoveries."""
        compiler = ReviewContextCompiler()
        result = compiler.compile(discovery_ir=None)
        assert result.discoveries == ()


# ---------------------------------------------------------------------------
# Tests: ReviewContextCompiler — Reference Assembly (Pass 4)
# ---------------------------------------------------------------------------

class TestReferenceAssembly:
    """Tests for reference assembly from discoveries."""

    def test_references_populated(self, sample_discovery_ir):
        """Test that references are populated from discoveries."""
        compiler = ReviewContextCompiler()
        result = compiler.compile(discovery_ir=sample_discovery_ir)
        assert len(result.references) > 0

    def test_references_deduplicated(self):
        """Test that references are deduplicated by id."""
        evidence = (
            DiscoveryEvidence(
                source="behavior",
                source_id="shared://ref/0",
                description="Shared evidence",
                evidence_ref="behavior://test/ref",
            ),
        )
        discoveries = [
            IRDiscovery(
                id="discovery://a/1",
                kind=IRDiscoveryKind.EXECUTION_DEPTH,
                statement="Discovery A",
                importance=0.5,
                evidence=evidence,
            ),
            IRDiscovery(
                id="discovery://b/1",
                kind=IRDiscoveryKind.SHARED_EXECUTION,
                statement="Discovery B",
                importance=0.5,
                evidence=evidence,
            ),
        ]
        discovery_ir = TestHelper.create_discovery_ir(discoveries)
        compiler = ReviewContextCompiler()
        result = compiler.compile(discovery_ir=discovery_ir)
        assert len(result.references) == 1

    def test_references_traceable(self, sample_discovery_ir):
        """Test that references are traceable to compiler artifacts."""
        compiler = ReviewContextCompiler()
        result = compiler.compile(discovery_ir=sample_discovery_ir)
        for ref in result.references:
            assert ref.compiler_artifact != ""
            assert ref.location != ""

    def test_references_empty_when_no_discoveries(self):
        """Test that no discoveries returns empty references."""
        compiler = ReviewContextCompiler()
        result = compiler.compile(discovery_ir=None)
        assert result.references == ()


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
            discovery_model=sample_discovery_model,
            discovery_ir=sample_discovery_ir,
        )
        assert isinstance(result, ReviewContext)
        assert isinstance(result.change, ChangeContext)
        assert isinstance(result.execution, ExecutionContext)
        assert isinstance(result.impact, ImpactContext)
        assert isinstance(result.state, StateContext)
        assert isinstance(result.integration, IntegrationContext)
        assert isinstance(result.validation, ValidationContext)
        assert isinstance(result.discoveries, tuple)
        assert isinstance(result.references, tuple)

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
            discovery_model=sample_discovery_model,
            discovery_ir=sample_discovery_ir,
        )
        assert result.change.summary.file_count > 0
        assert len(result.change.files) > 0
        assert len(result.execution.entry_points) > 0
        assert len(result.impact.modules) > 0
        assert len(result.discoveries) > 0
        assert len(result.references) > 0

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
            discovery_model=sample_discovery_model,
            discovery_ir=sample_discovery_ir,
        )
        result2 = compiler.compile(
            change_model=sample_change_model,
            behavior_model=sample_behavior_model,
            operational_model=sample_operational_model,
            discovery_model=sample_discovery_model,
            discovery_ir=sample_discovery_ir,
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
            discovery_model=sample_discovery_model,
            discovery_ir=sample_discovery_ir,
        )
        with pytest.raises(AttributeError):
            result.change = ChangeContext()  # type: ignore

    def test_no_graph_traversal(
        self,
        sample_change_model,
        sample_behavior_model,
        sample_operational_model,
        sample_discovery_model,
        sample_discovery_ir,
    ):
        """Structural test: compiler should not perform graph traversal."""
        compiler = ReviewContextCompiler()
        result = compiler.compile(
            change_model=sample_change_model,
            behavior_model=sample_behavior_model,
            operational_model=sample_operational_model,
            discovery_model=sample_discovery_model,
            discovery_ir=sample_discovery_ir,
        )
        assert isinstance(result.execution.max_execution_depth, int)
        assert isinstance(result.impact.fan_in, int)
        assert isinstance(result.impact.fan_out, int)
        assert isinstance(result.impact.boundary_crossings, int)


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
        assert result.execution.max_execution_depth == 0

    def test_empty_discovery_ir(self):
        """Test with an empty DiscoveryIR."""
        discovery_ir = TestHelper.create_discovery_ir([])
        compiler = ReviewContextCompiler()
        result = compiler.compile(discovery_ir=discovery_ir)
        assert result.discoveries == ()
        assert result.references == ()

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
        """Test with only DiscoveryIR provided."""
        compiler = ReviewContextCompiler()
        result = compiler.compile(discovery_ir=sample_discovery_ir)
        assert len(result.discoveries) > 0
        assert result.change.summary.file_count == 0
        assert result.execution.entry_points == ()

    def test_discovery_without_evidence(self):
        """Test that a discovery without evidence still appears."""
        discoveries = [
            IRDiscovery(
                id="discovery://no_evidence/1",
                kind=IRDiscoveryKind.EXECUTION_DEPTH,
                statement="Discovery without evidence",
                importance=0.5,
                evidence=(),
            ),
        ]
        discovery_ir = TestHelper.create_discovery_ir(discoveries)
        compiler = ReviewContextCompiler()
        result = compiler.compile(discovery_ir=discovery_ir)
        assert len(result.discoveries) == 1
        assert result.discoveries[0].references == ()
        assert len(result.references) == 0


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

    def test_impact_context_immutable(self):
        """Test that ImpactContext is frozen."""
        ctx = ImpactContext()
        with pytest.raises(AttributeError):
            ctx.services = ("svc1",)  # type: ignore

    def test_state_context_immutable(self):
        """Test that StateContext is frozen."""
        ctx = StateContext()
        with pytest.raises(AttributeError):
            ctx.models = ("Model1",)  # type: ignore

    def test_integration_context_immutable(self):
        """Test that IntegrationContext is frozen."""
        ctx = IntegrationContext()
        with pytest.raises(AttributeError):
            ctx.rest = ("/api/v1",)  # type: ignore

    def test_validation_context_immutable(self):
        """Test that ValidationContext is frozen."""
        ctx = ValidationContext()
        with pytest.raises(AttributeError):
            ctx.unit_tests = ("test_a",)  # type: ignore

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
        assert ctx.impact.services == ()
        assert ctx.state.models == ()
        assert ctx.integration.rest == ()
        assert ctx.validation.unit_tests == ()
        assert ctx.discoveries == ()
        assert ctx.references == ()

    def test_review_context_all_fields_present(self):
        """Test that ReviewContext has all required fields."""
        ctx = ReviewContext()
        assert hasattr(ctx, 'change')
        assert hasattr(ctx, 'execution')
        assert hasattr(ctx, 'impact')
        assert hasattr(ctx, 'state')
        assert hasattr(ctx, 'integration')
        assert hasattr(ctx, 'validation')
        assert hasattr(ctx, 'discoveries')
        assert hasattr(ctx, 'references')

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
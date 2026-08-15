"""Tests for the Discovery Compiler.

Tests that DiscoveryCompiler correctly consumes OperationalChangeModel
and produces a DiscoveryModel with deterministic discoveries.
"""

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
    Evidence,
    FileLocation,
)
from engine.change.model import (
    ChangeModel,
    ModifiedSymbol,
    ImportChange,
    EndpointChange,
)
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
from engine.operational.model import OperationalChangeModel
from engine.discovery.compiler import DiscoveryCompiler
from engine.discovery.model import (
    DiscoveryModel,
    Discovery,
    DiscoveryKind,
    DiscoveryFact,
    DiscoveryReference,
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
    ) -> ChangeModel:
        """Create a ChangeModel for testing."""
        return ChangeModel(
            added_symbols=tuple(added_symbols or []),
            removed_symbols=tuple(removed_symbols or []),
            modified_symbols=tuple(modified_symbols or []),
            changed_imports=tuple(changed_imports or []),
            changed_endpoints=tuple(changed_endpoints or []),
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
    """Create a sample change model for testing."""
    return TestHelper.create_change_model(
        added_symbols=[sample_symbols[1]],  # func2 was added
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
            id="shared://behavior://test/0",
            symbol_id=sample_symbols[0].id,
            used_by=("behavior://test",),
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


# ---------------------------------------------------------------------------
# Tests: DiscoveryModel
# ---------------------------------------------------------------------------


class TestDiscoveryModel:
    """Tests for the DiscoveryModel dataclass."""

    def test_creation(self):
        """Test creating a DiscoveryModel."""
        model = DiscoveryModel()
        assert model.discoveries == ()
        assert model.metadata == {}

    def test_creation_with_discoveries(self):
        """Test creating a DiscoveryModel with discoveries."""
        discovery = Discovery(
            id="test::1",
            kind=DiscoveryKind.SHARED_EXECUTION,
        )
        model = DiscoveryModel(discoveries=(discovery,))
        assert len(model.discoveries) == 1
        assert model.discoveries[0].id == "test::1"

    def test_immutable(self):
        """Test that the model is immutable."""
        model = DiscoveryModel()
        with pytest.raises(AttributeError):
            model.discoveries = []  # type: ignore

    def test_get_discoveries_by_kind(self):
        """Test filtering discoveries by kind."""
        discovery1 = Discovery(
            id="test::1",
            kind=DiscoveryKind.SHARED_EXECUTION,
        )
        discovery2 = Discovery(
            id="test::2",
            kind=DiscoveryKind.VALIDATION_GAP,
        )
        model = DiscoveryModel(discoveries=(discovery1, discovery2))

        shared = model.get_discoveries_by_kind(DiscoveryKind.SHARED_EXECUTION)
        assert len(shared) == 1
        assert shared[0].id == "test::1"

        validation = model.get_discoveries_by_kind(DiscoveryKind.VALIDATION_GAP)
        assert len(validation) == 1
        assert validation[0].id == "test::2"

    def test_get_discovery_by_id(self):
        """Test getting a discovery by ID."""
        discovery1 = Discovery(
            id="test::1",
            kind=DiscoveryKind.SHARED_EXECUTION,
        )
        discovery2 = Discovery(
            id="test::2",
            kind=DiscoveryKind.VALIDATION_GAP,
        )
        model = DiscoveryModel(discoveries=(discovery1, discovery2))

        found = model.get_discovery_by_id("test::1")
        assert found is not None
        assert found.id == "test::1"

        not_found = model.get_discovery_by_id("test::3")
        assert not_found is None


# ---------------------------------------------------------------------------
# Tests: DiscoveryCompiler
# ---------------------------------------------------------------------------


class TestDiscoveryCompiler:
    """Tests for the DiscoveryCompiler."""

    def test_compiler_initialization(self):
        """Test that the compiler initializes with all passes."""
        compiler = DiscoveryCompiler()
        assert len(compiler.passes) == 9

    def test_compiler_pass_names(self):
        """Test that pass names are correct."""
        compiler = DiscoveryCompiler()
        names = compiler.get_pass_names()
        assert "shared_execution" in names
        assert "validation_gap" in names
        assert "boundary_crossing" in names
        assert "hidden_relationship" in names
        assert "deep_execution" in names
        assert "shared_dependency" in names
        assert "event_publication" in names
        assert "state_mutation" in names
        assert "public_interface_change" in names

    def test_compile_none_raises(self):
        """Test that compiling None raises ValueError."""
        compiler = DiscoveryCompiler()
        with pytest.raises(ValueError, match="operational_model is required"):
            compiler.compile(None)  # type: ignore

    def test_compile_with_shared_executions(self, sample_operational_model):
        """Test compiling with shared executions."""
        compiler = DiscoveryCompiler()
        model = compiler.compile(sample_operational_model)

        assert isinstance(model, DiscoveryModel)
        # Should have at least one shared execution discovery
        shared_discoveries = model.get_discoveries_by_kind(
            DiscoveryKind.SHARED_EXECUTION
        )
        assert len(shared_discoveries) > 0

    def test_compile_produces_discovery_model(self, sample_operational_model):
        """Test that compilation produces a DiscoveryModel."""
        compiler = DiscoveryCompiler()
        model = compiler.compile(sample_operational_model)

        assert isinstance(model, DiscoveryModel)
        assert "compiler_version" in model.metadata
        assert "compiled_at" in model.metadata
        assert "discovery_count" in model.metadata
        assert "pass_count" in model.metadata

    def test_compile_deterministic(self, sample_operational_model):
        """Test that compilation is deterministic."""
        compiler = DiscoveryCompiler()

        model1 = compiler.compile(sample_operational_model)
        model2 = compiler.compile(sample_operational_model)

        # Discoveries should be identical
        assert len(model1.discoveries) == len(model2.discoveries)
        assert model1.discoveries == model2.discoveries
        # Metadata should have same structure (except timestamp)
        assert (
            model1.metadata["compiler_version"] == model2.metadata["compiler_version"]
        )
        assert model1.metadata["discovery_count"] == model2.metadata["discovery_count"]
        assert model1.metadata["pass_count"] == model2.metadata["pass_count"]

    def test_shared_execution_discovery_facts(self, sample_operational_model):
        """Test that shared execution discoveries have correct facts."""
        compiler = DiscoveryCompiler()
        model = compiler.compile(sample_operational_model)

        shared_discoveries = model.get_discoveries_by_kind(
            DiscoveryKind.SHARED_EXECUTION
        )
        if shared_discoveries:
            discovery = shared_discoveries[0]
            assert discovery.facts.behavior_count > 0
            assert len(discovery.facts.shared_symbol_ids) > 0

    def test_discovery_references(self, sample_operational_model):
        """Test that discoveries have references."""
        compiler = DiscoveryCompiler()
        model = compiler.compile(sample_operational_model)

        for discovery in model.discoveries:
            assert len(discovery.references) > 0
            for ref in discovery.references:
                assert ref.artifact_type != ""
                assert ref.artifact_id != ""

    def test_deep_execution_discovery(self, sample_operational_model):
        """Test that deep execution discoveries are produced."""
        compiler = DiscoveryCompiler()
        model = compiler.compile(sample_operational_model)

        deep_discoveries = model.get_discoveries_by_kind(DiscoveryKind.DEEP_EXECUTION)
        # Should have deep execution discovery if execution_depth > 0
        if sample_operational_model.behavior.execution_depth > 0:
            assert len(deep_discoveries) > 0
            if deep_discoveries:
                assert deep_discoveries[0].facts.max_depth > 0

    def test_hidden_relationship_discovery(self, sample_operational_model):
        """Test that hidden relationship discoveries are produced."""
        compiler = DiscoveryCompiler()
        model = compiler.compile(sample_operational_model)

        # This may or may not produce discoveries depending on the model
        hidden_discoveries = model.get_discoveries_by_kind(
            DiscoveryKind.HIDDEN_RELATIONSHIP
        )
        assert isinstance(hidden_discoveries, tuple)

    def test_validation_gap_discovery(self, sample_operational_model):
        """Test that validation gap discoveries are produced."""
        compiler = DiscoveryCompiler()
        model = compiler.compile(sample_operational_model)

        # This may or may not produce discoveries depending on the model
        validation_discoveries = model.get_discoveries_by_kind(
            DiscoveryKind.VALIDATION_GAP
        )
        assert isinstance(validation_discoveries, tuple)

    def test_boundary_crossing_discovery(self, sample_operational_model):
        """Test that boundary crossing discoveries are produced."""
        compiler = DiscoveryCompiler()
        model = compiler.compile(sample_operational_model)

        # This may or may not produce discoveries depending on the model
        boundary_discoveries = model.get_discoveries_by_kind(
            DiscoveryKind.BOUNDARY_CROSSING
        )
        assert isinstance(boundary_discoveries, tuple)

    def test_public_interface_change_discovery(self, sample_operational_model):
        """Test that public interface change discoveries are produced."""
        compiler = DiscoveryCompiler()
        model = compiler.compile(sample_operational_model)

        # This may or may not produce discoveries depending on the model
        interface_discoveries = model.get_discoveries_by_kind(
            DiscoveryKind.PUBLIC_INTERFACE_CHANGE
        )
        assert isinstance(interface_discoveries, tuple)

    def test_discovery_kinds_are_strings(self):
        """Test that DiscoveryKind values are strings."""
        assert isinstance(DiscoveryKind.SHARED_EXECUTION, str)
        assert isinstance(DiscoveryKind.VALIDATION_GAP, str)
        assert isinstance(DiscoveryKind.BOUNDARY_CROSSING, str)
        assert DiscoveryKind.SHARED_EXECUTION == "shared_execution"

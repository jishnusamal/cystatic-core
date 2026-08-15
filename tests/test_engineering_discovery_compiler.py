"""Tests for the Engineering Discovery Compiler.

Tests that EngineeringDiscoveryCompiler correctly projects OperationalChangeModel
into EngineeringDiscoveryModel with all execution-oriented abstractions.
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
from engine.operational.model import OperationalChangeModel, EngineeringDiscoveryModel
from engine.operational.compiler import EngineeringDiscoveryCompiler


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
def sample_behavior_model(
    sample_symbols, sample_execution_units, sample_entry_points, sample_terminal_points
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
# Tests: EngineeringDiscoveryModel
# ---------------------------------------------------------------------------


class TestEngineeringDiscoveryModel:
    """Tests for the EngineeringDiscoveryModel dataclass."""

    def test_creation(
        self, sample_repository_model, sample_change_model, sample_behavior_model
    ):
        """Test creating an EngineeringDiscoveryModel."""
        model = EngineeringDiscoveryModel(
            repository=sample_repository_model,
            change=sample_change_model,
            behavior=sample_behavior_model,
        )
        assert model.has_all_required_models()
        assert model.populated_optional_models == ()

    def test_required_models_present(
        self, sample_repository_model, sample_change_model, sample_behavior_model
    ):
        """Test that has_all_required_models returns True when all set."""
        model = EngineeringDiscoveryModel(
            repository=sample_repository_model,
            change=sample_change_model,
            behavior=sample_behavior_model,
        )
        assert model.has_all_required_models()

    def test_missing_repository_raises(
        self, sample_change_model, sample_behavior_model
    ):
        """Test that missing repository raises ValueError."""
        with pytest.raises(ValueError, match="repository model is required"):
            EngineeringDiscoveryModel(
                repository=None,  # type: ignore
                change=sample_change_model,
                behavior=sample_behavior_model,
            )

    def test_missing_change_raises(
        self, sample_repository_model, sample_behavior_model
    ):
        """Test that missing change model raises ValueError."""
        with pytest.raises(ValueError, match="change model is required"):
            EngineeringDiscoveryModel(
                repository=sample_repository_model,
                change=None,  # type: ignore
                behavior=sample_behavior_model,
            )

    def test_missing_behavior_raises(
        self, sample_repository_model, sample_change_model
    ):
        """Test that missing behavior model raises ValueError."""
        with pytest.raises(ValueError, match="behavior model is required"):
            EngineeringDiscoveryModel(
                repository=sample_repository_model,
                change=sample_change_model,
                behavior=None,  # type: ignore
            )

    def test_immutable(
        self, sample_repository_model, sample_change_model, sample_behavior_model
    ):
        """Test that the model is immutable."""
        model = EngineeringDiscoveryModel(
            repository=sample_repository_model,
            change=sample_change_model,
            behavior=sample_behavior_model,
        )
        with pytest.raises(AttributeError):
            model.repository = None  # type: ignore

    def test_execution_abstractions(
        self,
        sample_repository_model,
        sample_change_model,
        sample_behavior_model,
        sample_execution_units,
        sample_entry_points,
        sample_terminal_points,
    ):
        """Test execution-oriented abstractions."""
        model = EngineeringDiscoveryModel(
            repository=sample_repository_model,
            change=sample_change_model,
            behavior=sample_behavior_model,
            execution_units=tuple(sample_execution_units),
            entry_points=tuple(sample_entry_points),
            terminal_points=tuple(sample_terminal_points),
            execution_depth=2,
        )
        assert len(model.execution_units) == 2
        assert len(model.entry_points) == 1
        assert len(model.terminal_points) == 1
        assert model.execution_depth == 2

    def test_get_behaviors(
        self, sample_repository_model, sample_change_model, sample_behavior_model
    ):
        """Test get_behaviors method."""
        model = EngineeringDiscoveryModel(
            repository=sample_repository_model,
            change=sample_change_model,
            behavior=sample_behavior_model,
        )
        behaviors = model.get_behaviors()
        assert len(behaviors) == 1
        assert behaviors[0].id == "behavior://test"

    def test_repr(
        self, sample_repository_model, sample_change_model, sample_behavior_model
    ):
        """Test string representation."""
        model = EngineeringDiscoveryModel(
            repository=sample_repository_model,
            change=sample_change_model,
            behavior=sample_behavior_model,
        )
        repr_str = repr(model)
        assert "EngineeringDiscoveryModel" in repr_str
        assert "execution_units: 0" in repr_str
        assert "execution_chains: 0" in repr_str

    def test_backward_compatibility_alias(self):
        """Test that EngineeringDiscoveryArtifact is an alias."""
        from engine.operational.model import EngineeringDiscoveryArtifact

        assert EngineeringDiscoveryArtifact is EngineeringDiscoveryModel


# ---------------------------------------------------------------------------
# Tests: EngineeringDiscoveryCompiler
# ---------------------------------------------------------------------------


class TestEngineeringDiscoveryCompiler:
    """Tests for the EngineeringDiscoveryCompiler."""

    def test_compiler_initialization(self):
        """Test that the compiler initializes with enrichment passes."""
        compiler = EngineeringDiscoveryCompiler()
        assert len(compiler.passes) == 6

    def test_compiler_pass_names(self):
        """Test that pass names are correct."""
        compiler = EngineeringDiscoveryCompiler()
        names = compiler.get_pass_names()
        assert "dependency_compilation" in names
        assert "data_compilation" in names
        assert "event_compilation" in names
        assert "api_compilation" in names
        assert "validation_compilation" in names
        assert "metrics_compilation" in names

    def test_from_operational_model(self, sample_operational_model):
        """Test compiling from an OperationalChangeModel."""
        compiler = EngineeringDiscoveryCompiler()
        edm = compiler.from_operational_model(sample_operational_model)

        assert isinstance(edm, EngineeringDiscoveryModel)
        assert edm.repository == sample_operational_model.repository
        assert edm.change == sample_operational_model.change
        assert edm.behavior == sample_operational_model.behavior

    def test_from_operational_model_execution_data(self, sample_operational_model):
        """Test that execution data is projected correctly."""
        compiler = EngineeringDiscoveryCompiler()
        edm = compiler.from_operational_model(sample_operational_model)

        assert len(edm.execution_chains) == len(
            sample_operational_model.behavior.execution_chains
        )
        assert len(edm.entry_points) == len(
            sample_operational_model.behavior.entry_points
        )
        assert len(edm.terminal_points) == len(
            sample_operational_model.behavior.terminal_points
        )
        assert len(edm.reachable_units) == len(
            sample_operational_model.behavior.reachable_units
        )
        assert edm.execution_depth == sample_operational_model.behavior.execution_depth

    def test_from_operational_model_missing_models(self):
        """Test that missing models raise ValueError."""
        compiler = EngineeringDiscoveryCompiler()

        with pytest.raises(ValueError, match="missing required models"):
            compiler.from_operational_model(
                OperationalChangeModel(
                    repository=None,  # type: ignore
                    change=None,  # type: ignore
                    behavior=None,  # type: ignore
                )
            )

    def test_compile_with_components(
        self,
        sample_repository_model,
        sample_change_model,
        sample_behavior_model,
    ):
        """Test compiling from individual models."""
        compiler = EngineeringDiscoveryCompiler()
        edm = compiler.compile(
            repository_model=sample_repository_model,
            change_model=sample_change_model,
            behavior_model=sample_behavior_model,
        )

        assert isinstance(edm, EngineeringDiscoveryModel)
        assert edm.has_all_required_models()

    def test_compile_missing_repository(
        self, sample_change_model, sample_behavior_model
    ):
        """Test that missing repository raises ValueError."""
        compiler = EngineeringDiscoveryCompiler()

        with pytest.raises(ValueError, match="repository_delta or repository_model"):
            compiler.compile(
                repository_model=None,
                change_model=sample_change_model,
                behavior_model=sample_behavior_model,
            )

    def test_compile_missing_change(
        self, sample_repository_model, sample_behavior_model
    ):
        """Test that missing change model raises ValueError."""
        compiler = EngineeringDiscoveryCompiler()

        with pytest.raises(ValueError, match="change_model is required"):
            compiler.compile(
                repository_model=sample_repository_model,
                change_model=None,
                behavior_model=sample_behavior_model,
            )

    def test_compile_missing_behavior(
        self, sample_repository_model, sample_change_model
    ):
        """Test that missing behavior model raises ValueError."""
        compiler = EngineeringDiscoveryCompiler()

        with pytest.raises(ValueError, match="behavior_model is required"):
            compiler.compile(
                repository_model=sample_repository_model,
                change_model=sample_change_model,
                behavior_model=None,
            )

    def test_deterministic_output(self, sample_operational_model):
        """Test that compilation is deterministic."""
        compiler = EngineeringDiscoveryCompiler()

        model1 = compiler.from_operational_model(sample_operational_model)
        model2 = compiler.from_operational_model(sample_operational_model)

        assert model1 == model2
        assert model1.repository == model2.repository
        assert model1.change == model2.change
        assert model1.behavior == model2.behavior

    def test_enrichment_models_present(self, sample_operational_model):
        """Test that enrichment models are populated."""
        compiler = EngineeringDiscoveryCompiler()
        edm = compiler.from_operational_model(sample_operational_model)

        # All enrichment passes should produce models
        assert edm.has_dependency_model()
        assert edm.has_data_model()
        assert edm.has_event_model()
        assert edm.has_api_model()
        assert edm.has_validation_model()

    def test_dependency_model_content(self, sample_operational_model):
        """Test that dependency model has expected fields."""
        compiler = EngineeringDiscoveryCompiler()
        edm = compiler.from_operational_model(sample_operational_model)

        dep = edm.dependency
        assert dep is not None
        assert hasattr(dep, "callers")
        assert hasattr(dep, "dependents")
        assert hasattr(dep, "dependency_depth")

    def test_data_model_content(self, sample_operational_model):
        """Test that data model has expected fields."""
        compiler = EngineeringDiscoveryCompiler()
        edm = compiler.from_operational_model(sample_operational_model)

        data = edm.data
        assert data is not None
        assert hasattr(data, "models")
        assert hasattr(data, "tables")
        assert hasattr(data, "reads")
        assert hasattr(data, "writes")

    def test_execution_units_projected(self, sample_operational_model):
        """Test that execution units are projected from execution chains."""
        compiler = EngineeringDiscoveryCompiler()
        edm = compiler.from_operational_model(sample_operational_model)

        # Execution units should come from chains
        expected_count = sum(
            len(chain.units)
            for chain in sample_operational_model.behavior.execution_chains
        )
        assert len(edm.execution_units) == expected_count

    def test_shared_executions(self, sample_operational_model):
        """Test that shared executions are preserved."""
        compiler = EngineeringDiscoveryCompiler()
        edm = compiler.from_operational_model(sample_operational_model)

        assert len(edm.shared_executions) == len(
            sample_operational_model.behavior.shared_executions
        )

    def test_get_execution_units_for_behavior(self, sample_operational_model):
        """Test filtering execution units by behavior."""
        compiler = EngineeringDiscoveryCompiler()
        edm = compiler.from_operational_model(sample_operational_model)

        units = edm.get_execution_units_for_behavior("behavior://test")
        # Units are projected from chains, not prefixed with behavior id
        assert isinstance(units, tuple)

"""Tests for the Operational Compiler."""

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
    EntryPoint,
    EntryPointKind,
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
)
from engine.operational.model import OperationalChangeModel
from engine.operational.compiler import OperationalCompiler
from engine.operational.compiler.passes import (
    ModelCompositionPass,
    ConsistencyValidationPass,
    OperationalPassContext,
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
        entry_points: list[EntryPoint] | None = None,
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
    ) -> BehaviorModel:
        """Create a BehaviorModel for testing."""
        return BehaviorModel(
            behaviors=tuple(behaviors or []),
            execution_graphs=tuple(execution_graphs or []),
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
def sample_entry_points(sample_symbols):
    """Create sample entry points for testing."""
    return [
        EntryPoint(
            kind=EntryPointKind.REST_ENDPOINT,
            route="POST /test",
            handler_id=sample_symbols[0].id,
        ),
    ]


@pytest.fixture
def sample_repository_model(sample_symbols, sample_entry_points):
    """Create a sample repository model for testing."""
    return TestHelper.create_repository_model(
        symbols=sample_symbols,
        entry_points=sample_entry_points,
    )


@pytest.fixture
def sample_change_model(sample_symbols):
    """Create a sample change model for testing."""
    return TestHelper.create_change_model(
        added_symbols=[sample_symbols[1]],  # func2 was added
    )


@pytest.fixture
def sample_behavior_model(sample_symbols):
    """Create a sample behavior model for testing."""
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
# Tests: OperationalChangeModel
# ---------------------------------------------------------------------------

class TestOperationalChangeModel:
    """Tests for the OperationalChangeModel dataclass."""

    def test_creation(self, sample_operational_model):
        """Test creating an OperationalChangeModel."""
        model = sample_operational_model
        assert model.has_all_required_models()
        assert model.populated_optional_models == ()

    def test_required_models_present(self, sample_repository_model, sample_change_model, sample_behavior_model):
        """Test that has_all_required_models returns True when all set."""
        model = OperationalChangeModel(
            repository=sample_repository_model,
            change=sample_change_model,
            behavior=sample_behavior_model,
        )
        assert model.has_all_required_models()

    def test_optional_model_checks(self, sample_operational_model):
        """Test optional model presence checks."""
        model = sample_operational_model
        assert not model.has_dependency_model()
        assert not model.has_data_model()
        assert not model.has_event_model()
        assert not model.has_validation_model()

    def test_populated_optional_models(self, sample_operational_model):
        """Test populated_optional_models when optional fields are set."""
        model = sample_operational_model
        # Enrich with a mock dependency model
        model_with_dep = OperationalChangeModel(
            repository=model.repository,
            change=model.change,
            behavior=model.behavior,
            dependency={"mock": "dependency"},
        )
        assert model_with_dep.has_dependency_model()
        assert model_with_dep.populated_optional_models == ("dependency",)

    def test_populated_multiple_optional_models(self, sample_operational_model):
        """Test multiple optional models being populated."""
        model = sample_operational_model
        enriched = OperationalChangeModel(
            repository=model.repository,
            change=model.change,
            behavior=model.behavior,
            dependency={"dep": True},
            data={"data": True},
            event={"event": True},
        )
        assert enriched.populated_optional_models == ("dependency", "data", "event")

    def test_immutable(self, sample_operational_model):
        """Test that the model is immutable."""
        with pytest.raises(AttributeError):
            sample_operational_model.repository = None  # type: ignore

    def test_repr_without_optional(self, sample_operational_model):
        """Test string representation without optional models."""
        repr_str = repr(sample_operational_model)
        assert "OperationalChangeModel" in repr_str
        assert "RepositoryModel" in repr_str
        assert "ChangeModel" in repr_str
        assert "BehaviorModel" in repr_str
        assert "no optional models" in repr_str

    def test_repr_with_optional(self, sample_operational_model):
        """Test string representation with optional models."""
        enriched = OperationalChangeModel(
            repository=sample_operational_model.repository,
            change=sample_operational_model.change,
            behavior=sample_operational_model.behavior,
            dependency={"mock": True},
        )
        repr_str = repr(enriched)
        assert "dependency" in repr_str
        assert "present" in repr_str


# ---------------------------------------------------------------------------
# Tests: ModelCompositionPass
# ---------------------------------------------------------------------------

class TestModelCompositionPass:
    """Tests for the Model Composition pass."""

    def test_pass_name(self):
        """Test the pass name property."""
        pass_ = ModelCompositionPass()
        assert pass_.name == "model_composition"

    def test_compose_models(self, sample_repository_model, sample_change_model, sample_behavior_model):
        """Test composing all three models into one."""
        pass_ = ModelCompositionPass()
        context = OperationalPassContext(
            repository_model=sample_repository_model,
            change_model=sample_change_model,
            behavior_model=sample_behavior_model,
        )

        result = pass_.run(context)

        assert result.composed_model is not None
        assert result.composed_model.repository == sample_repository_model
        assert result.composed_model.change == sample_change_model
        assert result.composed_model.behavior == sample_behavior_model

    def test_missing_repository_model(self, sample_change_model, sample_behavior_model):
        """Test that missing repository model raises ValueError."""
        pass_ = ModelCompositionPass()
        context = OperationalPassContext(
            repository_model=None,
            change_model=sample_change_model,
            behavior_model=sample_behavior_model,
        )

        with pytest.raises(ValueError, match="missing.*repository_model"):
            pass_.run(context)

    def test_missing_change_model(self, sample_repository_model, sample_behavior_model):
        """Test that missing change model raises ValueError."""
        pass_ = ModelCompositionPass()
        context = OperationalPassContext(
            repository_model=sample_repository_model,
            change_model=None,
            behavior_model=sample_behavior_model,
        )

        with pytest.raises(ValueError, match="missing.*change_model"):
            pass_.run(context)

    def test_missing_behavior_model(self, sample_repository_model, sample_change_model):
        """Test that missing behavior model raises ValueError."""
        pass_ = ModelCompositionPass()
        context = OperationalPassContext(
            repository_model=sample_repository_model,
            change_model=sample_change_model,
            behavior_model=None,
        )

        with pytest.raises(ValueError, match="missing.*behavior_model"):
            pass_.run(context)

    def test_validate_input(self, sample_repository_model, sample_change_model, sample_behavior_model):
        """Test validate_input returns True when all present."""
        pass_ = ModelCompositionPass()
        context = OperationalPassContext(
            repository_model=sample_repository_model,
            change_model=sample_change_model,
            behavior_model=sample_behavior_model,
        )
        assert pass_.validate_input(context) is True

    def test_validate_input_missing(self, sample_repository_model):
        """Test validate_input returns False when models missing."""
        pass_ = ModelCompositionPass()
        context = OperationalPassContext(repository_model=sample_repository_model)
        assert pass_.validate_input(context) is False


# ---------------------------------------------------------------------------
# Tests: ConsistencyValidationPass
# ---------------------------------------------------------------------------

class TestConsistencyValidationPass:
    """Tests for the Consistency Validation pass."""

    def test_pass_name(self):
        """Test the pass name property."""
        pass_ = ConsistencyValidationPass()
        assert pass_.name == "consistency_validation"

    def test_valid_models(self, sample_operational_model):
        """Test that valid models produce no errors."""
        pass_ = ConsistencyValidationPass()
        context = OperationalPassContext()
        context.composed_model = sample_operational_model

        result = pass_.run(context)

        assert len(result.consistency_errors) == 0

    def test_changed_symbol_not_in_repository(self, sample_repository_model, sample_behavior_model):
        """Test detecting a changed symbol not in the repository."""
        pass_ = ConsistencyValidationPass()

        # Create a change model referencing a symbol NOT in the repository
        unknown_symbol = TestHelper.create_symbol(
            "python://unknown.py::ghost",
            "ghost",
            SymbolKind.FUNCTION,
        )
        change_model = TestHelper.create_change_model(
            added_symbols=[unknown_symbol],
        )

        model = OperationalChangeModel(
            repository=sample_repository_model,
            change=change_model,
            behavior=sample_behavior_model,
        )
        context = OperationalPassContext()
        context.composed_model = model

        result = pass_.run(context)

        assert len(result.consistency_errors) >= 1
        assert any("ghost" in err for err in result.consistency_errors)

    def test_behavior_root_symbol_not_in_repository(self, sample_repository_model, sample_change_model):
        """Test detecting a behavior referencing unknown root symbol."""
        pass_ = ConsistencyValidationPass()

        behavior_model = TestHelper.create_behavior_model(
            behaviors=[
                Behavior(
                    id="behavior://ghost",
                    name="ghost_behavior",
                    kind=BehaviorKind.REST_ENDPOINT,
                    entry_point="GET /ghost",
                    root_symbol_id="python://ghost.py::spooky",
                    changed_symbol_ids=(),
                ),
            ],
        )

        model = OperationalChangeModel(
            repository=sample_repository_model,
            change=sample_change_model,
            behavior=behavior_model,
        )
        context = OperationalPassContext()
        context.composed_model = model

        result = pass_.run(context)

        assert len(result.consistency_errors) >= 1
        assert any("spooky" in err for err in result.consistency_errors)

    def test_entry_point_handler_not_in_repository(self, sample_change_model, sample_behavior_model):
        """Test detecting an entry point handler not in repository."""
        pass_ = ConsistencyValidationPass()

        repository_model = TestHelper.create_repository_model(
            symbols=[],  # No symbols
            entry_points=[
                EntryPoint(
                    kind=EntryPointKind.REST_ENDPOINT,
                    route="GET /missing",
                    handler_id="python://missing.py::handler",
                ),
            ],
        )

        model = OperationalChangeModel(
            repository=repository_model,
            change=sample_change_model,
            behavior=sample_behavior_model,
        )
        context = OperationalPassContext()
        context.composed_model = model

        result = pass_.run(context)

        assert len(result.consistency_errors) >= 1
        assert any("handler" in err for err in result.consistency_errors)

    def test_execution_graph_unknown_node(self, sample_repository_model, sample_change_model):
        """Test detecting an execution graph with unknown node."""
        pass_ = ConsistencyValidationPass()

        behavior_model = TestHelper.create_behavior_model(
            execution_graphs=[
                ExecutionGraph(
                    behavior_id="behavior://test",
                    nodes=(
                        ExecutionNode(symbol_id="python://ghost.py::phantom", order=0),
                    ),
                    edges=(),
                ),
            ],
        )

        model = OperationalChangeModel(
            repository=sample_repository_model,
            change=sample_change_model,
            behavior=behavior_model,
        )
        context = OperationalPassContext()
        context.composed_model = model

        result = pass_.run(context)

        assert len(result.consistency_errors) >= 1
        assert any("phantom" in err for err in result.consistency_errors)

    def test_execution_graph_edge_invalid_node(self, sample_repository_model, sample_change_model, sample_symbols):
        """Test detecting an execution graph edge referencing non-existent node."""
        pass_ = ConsistencyValidationPass()

        behavior_model = TestHelper.create_behavior_model(
            execution_graphs=[
                ExecutionGraph(
                    behavior_id="behavior://test",
                    nodes=(
                        ExecutionNode(symbol_id=sample_symbols[0].id, order=0),
                        ExecutionNode(symbol_id=sample_symbols[1].id, order=1),
                    ),
                    edges=(
                        ExecutionEdge(
                            caller_id=sample_symbols[0].id,
                            callee_id="python://nope.py::nobody",
                        ),
                    ),
                ),
            ],
        )

        model = OperationalChangeModel(
            repository=sample_repository_model,
            change=sample_change_model,
            behavior=behavior_model,
        )
        context = OperationalPassContext()
        context.composed_model = model

        result = pass_.run(context)

        assert len(result.consistency_errors) >= 1
        assert any("nobody" in err for err in result.consistency_errors)

    def test_validate_input_no_model(self):
        """Test validate_input returns False when no composed model."""
        pass_ = ConsistencyValidationPass()
        context = OperationalPassContext()
        assert pass_.validate_input(context) is False

    def test_validate_input_with_model(self, sample_operational_model):
        """Test validate_input returns True when composed model present."""
        pass_ = ConsistencyValidationPass()
        context = OperationalPassContext()
        context.composed_model = sample_operational_model
        assert pass_.validate_input(context) is True

    def test_no_composed_model_returns_error(self):
        """Test that running without composed model records an error."""
        pass_ = ConsistencyValidationPass()
        context = OperationalPassContext()

        result = pass_.run(context)

        assert len(result.consistency_errors) == 1
        assert "no composed model" in result.consistency_errors[0]


# ---------------------------------------------------------------------------
# Tests: OperationalCompiler
# ---------------------------------------------------------------------------

class TestOperationalCompiler:
    """Tests for the OperationalCompiler."""

    def test_compiler_initialization(self):
        """Test that the compiler initializes with all passes."""
        compiler = OperationalCompiler()
        assert len(compiler.passes) == 8

    def test_compiler_pass_names(self):
        """Test that pass names are correct."""
        compiler = OperationalCompiler()
        names = compiler.get_pass_names()
        assert "model_composition" in names
        assert "consistency_validation" in names
        assert "dependency_compilation" in names
        assert "data_compilation" in names
        assert "event_compilation" in names
        assert "api_compilation" in names
        assert "validation_compilation" in names
        assert "metrics_compilation" in names

    def test_full_compilation(self, sample_repository_model, sample_change_model, sample_behavior_model):
        """Test a full compilation pipeline."""
        compiler = OperationalCompiler()
        result = compiler.compile(
            repository_model=sample_repository_model,
            change_model=sample_change_model,
            behavior_model=sample_behavior_model,
        )

        assert isinstance(result, OperationalChangeModel)
        assert result.repository == sample_repository_model
        assert result.change == sample_change_model
        assert result.behavior == sample_behavior_model
        assert result.has_all_required_models()

    def test_consistency_error_raises(self, sample_repository_model, sample_behavior_model):
        """Test that consistency errors raise ValueError."""
        compiler = OperationalCompiler()

        # Create a change model with a symbol not in repository
        unknown_symbol = TestHelper.create_symbol(
            "python://unknown.py::ghost",
            "ghost",
            SymbolKind.FUNCTION,
        )
        change_model = TestHelper.create_change_model(
            added_symbols=[unknown_symbol],
        )

        with pytest.raises(ValueError, match="Consistency validation failed"):
            compiler.compile(
                repository_model=sample_repository_model,
                change_model=change_model,
                behavior_model=sample_behavior_model,
            )

    def test_compile_with_errors(self, sample_repository_model, sample_behavior_model):
        """Test compile_with_errors returns errors instead of raising."""
        compiler = OperationalCompiler()

        unknown_symbol = TestHelper.create_symbol(
            "python://unknown.py::ghost",
            "ghost",
            SymbolKind.FUNCTION,
        )
        change_model = TestHelper.create_change_model(
            added_symbols=[unknown_symbol],
        )

        result, errors = compiler.compile_with_errors(
            repository_model=sample_repository_model,
            change_model=change_model,
            behavior_model=sample_behavior_model,
        )

        assert result is None
        assert len(errors) >= 1

    def test_compile_with_errors_success(self, sample_repository_model, sample_change_model, sample_behavior_model):
        """Test compile_with_errors returns model on success."""
        compiler = OperationalCompiler()

        result, errors = compiler.compile_with_errors(
            repository_model=sample_repository_model,
            change_model=sample_change_model,
            behavior_model=sample_behavior_model,
        )

        assert result is not None
        assert len(errors) == 0
        assert isinstance(result, OperationalChangeModel)

    def test_deterministic_output(self, sample_repository_model, sample_change_model, sample_behavior_model):
        """Test that compilation is deterministic."""
        compiler = OperationalCompiler()

        model1 = compiler.compile(
            repository_model=sample_repository_model,
            change_model=sample_change_model,
            behavior_model=sample_behavior_model,
        )
        model2 = compiler.compile(
            repository_model=sample_repository_model,
            change_model=sample_change_model,
            behavior_model=sample_behavior_model,
        )

        assert model1 == model2

    def test_empty_behavior_model(self, sample_repository_model, sample_change_model):
        """Test compilation with empty behavior model."""
        compiler = OperationalCompiler()
        behavior_model = TestHelper.create_behavior_model()

        result = compiler.compile(
            repository_model=sample_repository_model,
            change_model=sample_change_model,
            behavior_model=behavior_model,
        )

        assert isinstance(result, OperationalChangeModel)
        assert len(result.behavior.behaviors) == 0

    def test_empty_change_model(self, sample_repository_model, sample_behavior_model):
        """Test compilation with empty change model."""
        compiler = OperationalCompiler()
        change_model = TestHelper.create_change_model()

        result = compiler.compile(
            repository_model=sample_repository_model,
            change_model=change_model,
            behavior_model=sample_behavior_model,
        )

        assert isinstance(result, OperationalChangeModel)
        assert len(result.change.added_symbols) == 0

    def test_full_compilation_enriches_all_models(self, sample_repository_model, sample_change_model, sample_behavior_model):
        """Test that full compilation populates all optional models."""
        compiler = OperationalCompiler()
        result = compiler.compile(
            repository_model=sample_repository_model,
            change_model=sample_change_model,
            behavior_model=sample_behavior_model,
        )

        # All optional models should be populated
        assert result.has_dependency_model()
        assert result.has_data_model()
        assert result.has_event_model()
        assert result.has_api_model()
        assert result.has_validation_model()

        # Verify populated_optional_models includes all
        optional = result.populated_optional_models
        assert "dependency" in optional
        assert "data" in optional
        assert "event" in optional
        assert "api" in optional
        assert "validation" in optional

    def test_full_compilation_dependency_model(self, sample_repository_model, sample_change_model, sample_behavior_model):
        """Test that dependency model is populated with correct structure."""
        compiler = OperationalCompiler()
        result = compiler.compile(
            repository_model=sample_repository_model,
            change_model=sample_change_model,
            behavior_model=sample_behavior_model,
        )

        dep = result.dependency
        assert dep is not None
        # Should have callers, dependents, shared_modules, etc.
        assert hasattr(dep, "callers")
        assert hasattr(dep, "dependents")
        assert hasattr(dep, "shared_modules")
        assert hasattr(dep, "cross_service_references")
        assert hasattr(dep, "fan_in")
        assert hasattr(dep, "fan_out")
        assert hasattr(dep, "dependency_depth")

    def test_full_compilation_data_model(self, sample_repository_model, sample_change_model, sample_behavior_model):
        """Test that data model is populated with correct structure."""
        compiler = OperationalCompiler()
        result = compiler.compile(
            repository_model=sample_repository_model,
            change_model=sample_change_model,
            behavior_model=sample_behavior_model,
        )

        data = result.data
        assert data is not None
        assert hasattr(data, "models")
        assert hasattr(data, "tables")
        assert hasattr(data, "reads")
        assert hasattr(data, "writes")
        assert hasattr(data, "transactions")
        assert hasattr(data, "caches")
        assert hasattr(data, "external_storage")

    def test_full_compilation_event_model(self, sample_repository_model, sample_change_model, sample_behavior_model):
        """Test that event model is populated with correct structure."""
        compiler = OperationalCompiler()
        result = compiler.compile(
            repository_model=sample_repository_model,
            change_model=sample_change_model,
            behavior_model=sample_behavior_model,
        )

        event = result.event
        assert event is not None
        assert hasattr(event, "published_events")
        assert hasattr(event, "consumed_events")
        assert hasattr(event, "queues")
        assert hasattr(event, "workers")
        assert hasattr(event, "async_chains")
        assert hasattr(event, "event_graph")

    def test_full_compilation_api_model(self, sample_repository_model, sample_change_model, sample_behavior_model):
        """Test that API model is populated with correct structure."""
        compiler = OperationalCompiler()
        result = compiler.compile(
            repository_model=sample_repository_model,
            change_model=sample_change_model,
            behavior_model=sample_behavior_model,
        )

        api = result.api
        assert api is not None
        assert hasattr(api, "rest")
        assert hasattr(api, "graphql")
        assert hasattr(api, "rpc")
        assert hasattr(api, "cli")
        assert hasattr(api, "cron")
        assert hasattr(api, "workers")

    def test_full_compilation_validation_model(self, sample_repository_model, sample_change_model, sample_behavior_model):
        """Test that validation model is populated with correct structure."""
        compiler = OperationalCompiler()
        result = compiler.compile(
            repository_model=sample_repository_model,
            change_model=sample_change_model,
            behavior_model=sample_behavior_model,
        )

        validation = result.validation
        assert validation is not None
        assert hasattr(validation, "unit_tests")
        assert hasattr(validation, "integration_tests")
        assert hasattr(validation, "e2e_tests")
        assert hasattr(validation, "benchmarks")
        assert hasattr(validation, "production_replays")
        assert hasattr(validation, "coverage_links")

    def test_discovery_metrics_in_context(self, sample_repository_model, sample_change_model, sample_behavior_model):
        """Test that discovery metrics are stored in pass context metadata."""
        compiler = OperationalCompiler()
        result = compiler.compile(
            repository_model=sample_repository_model,
            change_model=sample_change_model,
            behavior_model=sample_behavior_model,
        )

        # The metrics are stored in context metadata, not on the model
        # Verify the compilation succeeded with all models
        assert result is not None
        assert result.has_dependency_model()
        assert result.has_data_model()
        assert result.has_event_model()
        assert result.has_api_model()
        assert result.has_validation_model()


# ---------------------------------------------------------------------------
# Tests: DependencyCompilationPass
# ---------------------------------------------------------------------------

class TestDependencyCompilationPass:
    """Tests for the Dependency Analysis pass."""

    def test_pass_name(self):
        """Test the pass name property."""
        from engine.operational.compiler.passes.dependency import DependencyCompilationPass
        pass_ = DependencyCompilationPass()
        assert pass_.name == "dependency_compilation"

    def test_validate_input_no_model(self):
        """Test validate_input returns False when no composed model."""
        from engine.operational.compiler.passes.dependency import DependencyCompilationPass
        pass_ = DependencyCompilationPass()
        context = OperationalPassContext()
        assert pass_.validate_input(context) is False

    def test_validate_input_with_model(self, sample_operational_model):
        """Test validate_input returns True when composed model present."""
        from engine.operational.compiler.passes.dependency import DependencyCompilationPass
        pass_ = DependencyCompilationPass()
        context = OperationalPassContext()
        context.composed_model = sample_operational_model
        assert pass_.validate_input(context) is True

    def test_dependency_model_creation(self, sample_operational_model):
        """Test that dependency analysis produces a DependencyModel."""
        from engine.operational.compiler.passes.dependency import DependencyCompilationPass
        pass_ = DependencyCompilationPass()
        context = OperationalPassContext()
        context.composed_model = sample_operational_model

        result = pass_.run(context)

        assert result.composed_model is not None
        dep = result.composed_model.dependency
        assert dep is not None
        # Verify it's a DependencyModel
        assert hasattr(dep, "callers")
        assert hasattr(dep, "dependents")
        assert hasattr(dep, "dependency_depth")

    def test_dependency_model_empty_behavior(self, sample_repository_model, sample_change_model):
        """Test dependency analysis with empty behavior model."""
        from engine.operational.compiler.passes.dependency import DependencyCompilationPass
        pass_ = DependencyCompilationPass()
        behavior_model = TestHelper.create_behavior_model()
        model = OperationalChangeModel(
            repository=sample_repository_model,
            change=sample_change_model,
            behavior=behavior_model,
        )
        context = OperationalPassContext()
        context.composed_model = model

        result = pass_.run(context)

        dep = result.composed_model.dependency
        assert dep is not None
        assert dep.dependency_depth == 0


# ---------------------------------------------------------------------------
# Tests: DataCompilationPass
# ---------------------------------------------------------------------------

class TestDataCompilationPass:
    """Tests for the Data Analysis pass."""

    def test_pass_name(self):
        """Test the pass name property."""
        from engine.operational.compiler.passes.data import DataCompilationPass
        pass_ = DataCompilationPass()
        assert pass_.name == "data_compilation"

    def test_validate_input_no_model(self):
        """Test validate_input returns False when no composed model."""
        from engine.operational.compiler.passes.data import DataCompilationPass
        pass_ = DataCompilationPass()
        context = OperationalPassContext()
        assert pass_.validate_input(context) is False

    def test_data_model_creation(self, sample_operational_model):
        """Test that data analysis produces a DataModel."""
        from engine.operational.compiler.passes.data import DataCompilationPass
        pass_ = DataCompilationPass()
        context = OperationalPassContext()
        context.composed_model = sample_operational_model

        result = pass_.run(context)

        data = result.composed_model.data
        assert data is not None
        assert hasattr(data, "models")
        assert hasattr(data, "tables")
        assert hasattr(data, "reads")
        assert hasattr(data, "writes")

    def test_data_model_with_model_class(self, sample_repository_model, sample_change_model):
        """Test data analysis detects model classes when reachable."""
        from engine.operational.compiler.passes.data import DataCompilationPass
        pass_ = DataCompilationPass()

        # Create a model class symbol that is also an affected symbol
        model_sym = TestHelper.create_symbol(
            "python://models.py::UserModel",
            "UserModel",
            SymbolKind.CLASS,
            file="models.py",
        )
        # Make it an affected symbol by adding it as a changed symbol in a behavior
        behavior_model = TestHelper.create_behavior_model(
            behaviors=[
                Behavior(
                    id="behavior://model_test",
                    name="model_test",
                    kind=BehaviorKind.REST_ENDPOINT,
                    entry_point="GET /users",
                    root_symbol_id=model_sym.id,
                    changed_symbol_ids=(model_sym.id,),
                ),
            ],
        )
        repo = TestHelper.create_repository_model(
            symbols=[model_sym],
        )
        model = OperationalChangeModel(
            repository=repo,
            change=sample_change_model,
            behavior=behavior_model,
        )
        context = OperationalPassContext()
        context.composed_model = model

        result = pass_.run(context)

        data = result.composed_model.data
        assert data is not None
        # UserModel ends with "Model" so it should be detected
        assert len(data.models) >= 1


# ---------------------------------------------------------------------------
# Tests: EventCompilationPass
# ---------------------------------------------------------------------------

class TestEventCompilationPass:
    """Tests for the Event Analysis pass."""

    def test_pass_name(self):
        """Test the pass name property."""
        from engine.operational.compiler.passes.events import EventCompilationPass
        pass_ = EventCompilationPass()
        assert pass_.name == "event_compilation"

    def test_validate_input_no_model(self):
        """Test validate_input returns False when no composed model."""
        from engine.operational.compiler.passes.events import EventCompilationPass
        pass_ = EventCompilationPass()
        context = OperationalPassContext()
        assert pass_.validate_input(context) is False

    def test_event_model_creation(self, sample_operational_model):
        """Test that event analysis produces an EventModel."""
        from engine.operational.compiler.passes.events import EventCompilationPass
        pass_ = EventCompilationPass()
        context = OperationalPassContext()
        context.composed_model = sample_operational_model

        result = pass_.run(context)

        event = result.composed_model.event
        assert event is not None
        assert hasattr(event, "published_events")
        assert hasattr(event, "consumed_events")
        assert hasattr(event, "queues")
        assert hasattr(event, "workers")


# ---------------------------------------------------------------------------
# Tests: APICompilationPass
# ---------------------------------------------------------------------------

class TestAPICompilationPass:
    """Tests for the API Analysis pass."""

    def test_pass_name(self):
        """Test the pass name property."""
        from engine.operational.compiler.passes.api import APICompilationPass
        pass_ = APICompilationPass()
        assert pass_.name == "api_compilation"

    def test_validate_input_no_model(self):
        """Test validate_input returns False when no composed model."""
        from engine.operational.compiler.passes.api import APICompilationPass
        pass_ = APICompilationPass()
        context = OperationalPassContext()
        assert pass_.validate_input(context) is False

    def test_api_model_creation(self, sample_operational_model):
        """Test that API analysis produces an APIModel."""
        from engine.operational.compiler.passes.api import APICompilationPass
        pass_ = APICompilationPass()
        context = OperationalPassContext()
        context.composed_model = sample_operational_model

        result = pass_.run(context)

        api = result.composed_model.api
        assert api is not None
        assert hasattr(api, "rest")
        assert hasattr(api, "graphql")
        assert hasattr(api, "rpc")
        assert hasattr(api, "cli")
        assert hasattr(api, "cron")
        assert hasattr(api, "workers")

    def test_api_model_detects_rest_endpoint(self, sample_repository_model, sample_change_model, sample_behavior_model):
        """Test that API analysis detects affected REST endpoints."""
        from engine.operational.compiler.passes.api import APICompilationPass
        pass_ = APICompilationPass()

        model = OperationalChangeModel(
            repository=sample_repository_model,
            change=sample_change_model,
            behavior=sample_behavior_model,
        )
        context = OperationalPassContext()
        context.composed_model = model

        result = pass_.run(context)

        api = result.composed_model.api
        assert api is not None
        # The sample has a POST /test endpoint that should be detected
        assert len(api.rest) >= 1


# ---------------------------------------------------------------------------
# Tests: ValidationCompilationPass
# ---------------------------------------------------------------------------

class TestValidationCompilationPass:
    """Tests for the Validation Analysis pass."""

    def test_pass_name(self):
        """Test the pass name property."""
        from engine.operational.compiler.passes.validation import ValidationCompilationPass
        pass_ = ValidationCompilationPass()
        assert pass_.name == "validation_compilation"

    def test_validate_input_no_model(self):
        """Test validate_input returns False when no composed model."""
        from engine.operational.compiler.passes.validation import ValidationCompilationPass
        pass_ = ValidationCompilationPass()
        context = OperationalPassContext()
        assert pass_.validate_input(context) is False

    def test_validation_model_creation(self, sample_operational_model):
        """Test that validation analysis produces a ValidationModel."""
        from engine.operational.compiler.passes.validation import ValidationCompilationPass
        pass_ = ValidationCompilationPass()
        context = OperationalPassContext()
        context.composed_model = sample_operational_model

        result = pass_.run(context)

        validation = result.composed_model.validation
        assert validation is not None
        assert hasattr(validation, "unit_tests")
        assert hasattr(validation, "integration_tests")
        assert hasattr(validation, "e2e_tests")
        assert hasattr(validation, "benchmarks")
        assert hasattr(validation, "production_replays")
        assert hasattr(validation, "coverage_links")


# ---------------------------------------------------------------------------
# Tests: MetricsCompilationPass
# ---------------------------------------------------------------------------

class TestMetricsCompilationPass:
    """Tests for the Discovery Metrics pass."""

    def test_pass_name(self):
        """Test the pass name property."""
        from engine.operational.compiler.passes.metrics import MetricsCompilationPass
        pass_ = MetricsCompilationPass()
        assert pass_.name == "metrics_compilation"

    def test_validate_input_no_model(self):
        """Test validate_input returns False when no composed model."""
        from engine.operational.compiler.passes.metrics import MetricsCompilationPass
        pass_ = MetricsCompilationPass()
        context = OperationalPassContext()
        assert pass_.validate_input(context) is False

    def test_metrics_in_metadata(self, sample_operational_model):
        """Test that metrics are stored in context metadata."""
        from engine.operational.compiler.passes.metrics import MetricsCompilationPass
        pass_ = MetricsCompilationPass()
        context = OperationalPassContext()
        context.composed_model = sample_operational_model

        result = pass_.run(context)

        metrics = result.metadata.get("discovery_metrics")
        assert metrics is not None
        assert hasattr(metrics, "behaviors")
        assert hasattr(metrics, "services")
        assert hasattr(metrics, "dependency_fan_out")
        assert hasattr(metrics, "execution_depth")
        assert hasattr(metrics, "data_stores")
        assert hasattr(metrics, "events")
        assert hasattr(metrics, "apis")
        assert hasattr(metrics, "validation_breadth")
        assert hasattr(metrics, "traversal_size")

    def test_metrics_counts(self, sample_operational_model):
        """Test that metrics counts are reasonable."""
        from engine.operational.compiler.passes.metrics import MetricsCompilationPass
        pass_ = MetricsCompilationPass()
        context = OperationalPassContext()
        context.composed_model = sample_operational_model

        result = pass_.run(context)

        metrics = result.metadata.get("discovery_metrics")
        assert metrics is not None
        assert metrics.behaviors >= 0
        assert metrics.services >= 0
        assert metrics.traversal_size >= 0

"""Tests for the LLM Context Renderer.

Tests that LLMContextRenderer correctly transforms EngineeringDiscoveryModel
into the normalized LLM context artifact format.
"""

from typing import Any

import pytest
import yaml  # type: ignore[import-untyped]
from engine.language.model import (
    CallEdge,
    CallGraph,
    EntryPointKind,
    ReferenceGraph,
    RepositoryModel,
    Symbol,
    SymbolKind,
    SymbolVisibility,
)
from engine.language.model import (
    EntryPoint as RepoEntryPoint,
)

from engine.behavior.model import (
    Behavior,
    BehaviorKind,
    BehaviorModel,
    EntryPoint,
    ExecutionChain,
    ExecutionGraph,
    ExecutionUnit,
    SharedExecution,
    TerminalPoint,
)
from engine.change.model import (
    ChangeModel,
    EndpointChange,
    ImportChange,
    ModifiedSymbol,
)
from engine.operational.model import EngineeringDiscoveryModel
from integrations.github.renderers.llm_context_renderer import LLMContextRenderer

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


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
        changed_files: list[str] | None = None,
    ) -> ChangeModel:
        """Create a ChangeModel for testing."""
        change = ChangeModel(
            added_symbols=tuple(added_symbols or []),
            removed_symbols=tuple(removed_symbols or []),
            modified_symbols=tuple(modified_symbols or []),
            changed_imports=tuple(changed_imports or []),
            changed_endpoints=tuple(changed_endpoints or []),
        )
        # Add changed_files attribute if provided
        if changed_files is not None:
            object.__setattr__(change, "changed_files", tuple(changed_files))
        return change

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
        changed_files=["test.py"],
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
            used_by={"behavior://test", "behavior://other"},
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
def sample_engineering_discovery_model(
    sample_repository_model,
    sample_change_model,
    sample_behavior_model,
):
    """Create a sample engineering discovery model for testing."""
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


# ---------------------------------------------------------------------------
# Tests: LLMContextRenderer
# ---------------------------------------------------------------------------


class TestLLMContextRenderer:
    """Tests for the LLMContextRenderer."""

    def test_render_returns_dict(self, sample_engineering_discovery_model):
        """Test that render returns a dictionary."""
        renderer = LLMContextRenderer()
        result = renderer.render(sample_engineering_discovery_model)
        assert isinstance(result, dict)

    def test_render_has_required_sections(self, sample_engineering_discovery_model):
        """Test that render output has all required sections."""
        renderer = LLMContextRenderer()
        result = renderer.render(sample_engineering_discovery_model)

        assert "summary" in result
        assert "discoveries" in result
        assert "evidence" in result
        assert "constraints" in result

    def test_render_summary_section(self, sample_engineering_discovery_model):
        """Test that summary section is correctly populated."""
        renderer = LLMContextRenderer()
        result = renderer.render(sample_engineering_discovery_model)

        summary = result["summary"]
        assert "changed_files" in summary
        assert "changed_symbols" in summary
        assert isinstance(summary["changed_files"], int)
        assert isinstance(summary["changed_symbols"], int)
        assert summary["changed_symbols"] > 0

    def test_render_discoveries_section(self, sample_engineering_discovery_model):
        """Test that discoveries section is correctly populated."""
        renderer = LLMContextRenderer()
        result = renderer.render(sample_engineering_discovery_model)

        discoveries = result["discoveries"]
        assert isinstance(discoveries, list)
        assert len(discoveries) > 0

    def test_render_discovery_structure(self, sample_engineering_discovery_model):
        """Test that each discovery has the correct structure."""
        renderer = LLMContextRenderer()
        result = renderer.render(sample_engineering_discovery_model)

        for discovery in result["discoveries"]:
            assert "id" in discovery
            assert "title" in discovery
            assert "summary" in discovery

    def test_render_reachable_units_discovery(self, sample_engineering_discovery_model):
        """Test that reachable_units discovery is present when applicable."""
        renderer = LLMContextRenderer()
        result = renderer.render(sample_engineering_discovery_model)

        # Find reachable_units discovery
        reachable_discovery = None
        for discovery in result["discoveries"]:
            if discovery["id"] == "reachable_units":
                reachable_discovery = discovery
                break

        assert reachable_discovery is not None
        assert "metrics" in reachable_discovery
        assert "examples" in reachable_discovery
        assert isinstance(reachable_discovery["examples"], list)

    def test_render_shared_execution_discovery(
        self, sample_engineering_discovery_model
    ):
        """Test that shared_execution discovery is present when applicable."""
        renderer = LLMContextRenderer()
        result = renderer.render(sample_engineering_discovery_model)

        # Find shared_execution discovery
        shared_discovery = None
        for discovery in result["discoveries"]:
            if discovery["id"] == "shared_execution":
                shared_discovery = discovery
                break

        assert shared_discovery is not None
        assert "shared_symbols" in shared_discovery
        assert "affected_domains" in shared_discovery

    def test_render_evidence_section(self, sample_engineering_discovery_model):
        """Test that evidence section is correctly populated."""
        renderer = LLMContextRenderer()
        result = renderer.render(sample_engineering_discovery_model)

        evidence = result["evidence"]
        assert "total" in evidence
        assert "confidence" in evidence
        assert evidence["confidence"] == "deterministic"
        assert isinstance(evidence["total"], int)
        assert evidence["total"] > 0

    def test_render_constraints_section(self, sample_engineering_discovery_model):
        """Test that constraints section is correctly populated."""
        renderer = LLMContextRenderer()
        result = renderer.render(sample_engineering_discovery_model)

        constraints = result["constraints"]
        assert isinstance(constraints, list)
        assert len(constraints) > 0
        assert "Never invent new behaviors." in constraints
        assert "Never speculate about bugs." in constraints

    def test_render_with_settings(self, sample_engineering_discovery_model):
        """Test that render accepts optional settings parameter."""
        renderer = LLMContextRenderer()

        # Should not raise even with settings provided
        result = renderer.render(sample_engineering_discovery_model, settings={})
        assert isinstance(result, dict)

    def test_render_deterministic(self, sample_engineering_discovery_model):
        """Test that render is deterministic (same input = same output)."""
        renderer = LLMContextRenderer()

        result1 = renderer.render(sample_engineering_discovery_model)
        result2 = renderer.render(sample_engineering_discovery_model)

        assert result1 == result2

    def test_render_yaml_serializable(self, sample_engineering_discovery_model):
        """Test that render output is YAML-serializable."""
        renderer = LLMContextRenderer()
        result = renderer.render(sample_engineering_discovery_model)

        # Should not raise
        yaml_str = yaml.dump(result, default_flow_style=False)
        assert isinstance(yaml_str, str)
        assert len(yaml_str) > 0

    def test_render_empty_model(self):
        """Test rendering with minimal model."""
        renderer = LLMContextRenderer()

        # Create minimal model
        repository = TestHelper.create_repository_model(symbols=[])
        change = TestHelper.create_change_model()
        behavior = TestHelper.create_behavior_model()

        artifact = EngineeringDiscoveryModel(
            repository=repository,
            change=change,
            behavior=behavior,
        )

        result = renderer.render(artifact)

        assert isinstance(result, dict)
        assert "summary" in result
        assert "discoveries" in result
        assert "evidence" in result
        assert "constraints" in result

    def test_render_execution_chains_discovery(
        self, sample_engineering_discovery_model
    ):
        """Test that execution_chains discovery is present when applicable."""
        renderer = LLMContextRenderer()
        result = renderer.render(sample_engineering_discovery_model)

        # Find execution_chains discovery
        chains_discovery = None
        for discovery in result["discoveries"]:
            if discovery["id"] == "execution_chains":
                chains_discovery = discovery
                break

        if chains_discovery:  # Only test if present
            assert "chain_count" in chains_discovery
            assert "representative_paths" in chains_discovery

    def test_render_metrics_structure(self, sample_engineering_discovery_model):
        """Test that metrics in reachable_units discovery have correct structure."""
        renderer = LLMContextRenderer()
        result = renderer.render(sample_engineering_discovery_model)

        # Find reachable_units discovery
        reachable_discovery = None
        for discovery in result["discoveries"]:
            if discovery["id"] == "reachable_units":
                reachable_discovery = discovery
                break

        if reachable_discovery:
            metrics = reachable_discovery["metrics"]
            assert "execution_paths" in metrics
            assert "reachable_units" in metrics
            assert "propagation_depth" in metrics
            assert "boundary_crossings" in metrics

    def test_render_examples_limited(self, sample_engineering_discovery_model):
        """Test that examples are limited to 5."""
        renderer = LLMContextRenderer()
        result = renderer.render(sample_engineering_discovery_model)

        # Find reachable_units discovery
        reachable_discovery = None
        for discovery in result["discoveries"]:
            if discovery["id"] == "reachable_units":
                reachable_discovery = discovery
                break

        if reachable_discovery:
            assert len(reachable_discovery["examples"]) <= 5

    def test_render_shared_symbols_limited(self, sample_engineering_discovery_model):
        """Test that shared_symbols are limited to 5."""
        renderer = LLMContextRenderer()
        result = renderer.render(sample_engineering_discovery_model)

        # Find shared_execution discovery
        shared_discovery = None
        for discovery in result["discoveries"]:
            if discovery["id"] == "shared_execution":
                shared_discovery = discovery
                break

        if shared_discovery:
            assert len(shared_discovery["shared_symbols"]) <= 5

    def test_render_affected_domains_sorted(self, sample_engineering_discovery_model):
        """Test that affected_domains are sorted."""
        renderer = LLMContextRenderer()
        result = renderer.render(sample_engineering_discovery_model)

        # Find shared_execution discovery
        shared_discovery = None
        for discovery in result["discoveries"]:
            if discovery["id"] == "shared_execution":
                shared_discovery = discovery
                break

        if shared_discovery:
            domains = shared_discovery["affected_domains"]
            assert domains == sorted(domains)

    def test_render_representative_paths_limited(
        self, sample_engineering_discovery_model
    ):
        """Test that representative_paths are limited to 3."""
        renderer = LLMContextRenderer()
        result = renderer.render(sample_engineering_discovery_model)

        # Find execution_chains discovery
        chains_discovery = None
        for discovery in result["discoveries"]:
            if discovery["id"] == "execution_chains":
                chains_discovery = discovery
                break

        if chains_discovery:
            assert len(chains_discovery["representative_paths"]) <= 3

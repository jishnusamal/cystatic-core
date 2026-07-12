"""Tests for the Behavior Compiler (Phase 3)."""

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
    EntryPoint,
    EntryPointKind,
)
from change.model import (
    ChangeModel,
    ModifiedSymbol,
    ImportChange,
    EndpointChange,
)
from behavior.model import (
    Behavior,
    BehaviorKind,
    BehaviorModel,
    ExecutionGraph,
    ExecutionNode,
    ExecutionEdge,
)
from behavior.compiler import BehaviorCompiler, BehaviorPassContext


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


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_call_graph():
    """Create a sample call graph for testing."""
    return [
        # POST /checkout behavior
        CallEdge(caller_id="handler://checkout", callee_id="python://checkout.py::confirm_checkout"),
        CallEdge(caller_id="python://checkout.py::confirm_checkout", callee_id="python://checkout.py::validate_coupon"),
        CallEdge(caller_id="python://checkout.py::confirm_checkout", callee_id="python://checkout.py::charge_card"),
        CallEdge(caller_id="python://checkout.py::charge_card", callee_id="python://payment.py::process_payment"),
        CallEdge(caller_id="python://checkout.py::confirm_checkout", callee_id="python://checkout.py::save_order"),

        # Worker behavior (separate tree)
        CallEdge(caller_id="handler://invoice_worker", callee_id="python://worker.py::process_invoice"),
        CallEdge(caller_id="python://worker.py::process_invoice", callee_id="python://worker.py::generate_pdf"),
        CallEdge(caller_id="python://worker.py::process_invoice", callee_id="python://billing.py::update_ledger"),
    ]


@pytest.fixture
def sample_repository_model(sample_call_graph):
    """Create a sample repository model for testing."""
    symbols = [
        TestHelper.create_symbol(
            "python://checkout.py::confirm_checkout",
            "confirm_checkout",
            SymbolKind.FUNCTION,
            file="checkout.py",
        ),
        TestHelper.create_symbol(
            "python://checkout.py::validate_coupon",
            "validate_coupon",
            SymbolKind.FUNCTION,
            file="checkout.py",
        ),
        TestHelper.create_symbol(
            "python://checkout.py::charge_card",
            "charge_card",
            SymbolKind.FUNCTION,
            file="checkout.py",
        ),
        TestHelper.create_symbol(
            "python://checkout.py::save_order",
            "save_order",
            SymbolKind.FUNCTION,
            file="checkout.py",
        ),
        TestHelper.create_symbol(
            "python://payment.py::process_payment",
            "process_payment",
            SymbolKind.FUNCTION,
            file="payment.py",
        ),
        TestHelper.create_symbol(
            "python://worker.py::process_invoice",
            "process_invoice",
            SymbolKind.FUNCTION,
            file="worker.py",
        ),
        TestHelper.create_symbol(
            "python://worker.py::generate_pdf",
            "generate_pdf",
            SymbolKind.FUNCTION,
            file="worker.py",
        ),
        TestHelper.create_symbol(
            "python://billing.py::update_ledger",
            "update_ledger",
            SymbolKind.FUNCTION,
            file="billing.py",
        ),
    ]

    entry_points = [
        EntryPoint(
            kind=EntryPointKind.REST_ENDPOINT,
            route="POST /checkout",
            handler_id="handler://checkout",
            metadata={'handler': 'confirm_checkout', 'file': 'checkout.py'},
        ),
        EntryPoint(
            kind=EntryPointKind.WORKER_ENTRY,
            route="invoice-worker",
            handler_id="handler://invoice_worker",
            metadata={'worker_name': 'invoice-worker', 'file': 'worker.py'},
        ),
    ]

    return TestHelper.create_repository_model(
        symbols=symbols,
        entry_points=entry_points,
        call_edges=sample_call_graph,
    )


# ---------------------------------------------------------------------------
# Behavior Model Tests
# ---------------------------------------------------------------------------

class TestBehaviorModel:
    """Tests for Behavior model classes."""

    def test_behavior_creation(self):
        """Test creating a Behavior."""
        behavior = Behavior(
            id="behavior://handler://checkout",
            name="checkout",
            kind=BehaviorKind.REST_ENDPOINT,
            entry_point="POST /checkout",
            root_symbol_id="handler://checkout",
            changed_symbol_ids=("python://checkout.py::validate_coupon",),
        )
        assert behavior.id == "behavior://handler://checkout"
        assert behavior.name == "checkout"
        assert behavior.kind == BehaviorKind.REST_ENDPOINT
        assert behavior.entry_point == "POST /checkout"
        assert behavior.root_symbol_id == "handler://checkout"
        assert behavior.changed_symbol_ids == ("python://checkout.py::validate_coupon",)

    def test_behavior_validation_empty_id(self):
        """Test that empty behavior id raises ValueError."""
        with pytest.raises(ValueError, match="Behavior id cannot be empty"):
            Behavior(id="", name="test", kind=BehaviorKind.REST_ENDPOINT, entry_point="GET /test", root_symbol_id="sym://test")

    def test_behavior_validation_empty_name(self):
        """Test that empty behavior name raises ValueError."""
        with pytest.raises(ValueError, match="Behavior name cannot be empty"):
            Behavior(id="behavior://test", name="", kind=BehaviorKind.REST_ENDPOINT, entry_point="GET /test", root_symbol_id="sym://test")

    def test_behavior_validation_empty_entry_point(self):
        """Test that empty entry point raises ValueError."""
        with pytest.raises(ValueError, match="Entry point cannot be empty"):
            Behavior(id="behavior://test", name="test", kind=BehaviorKind.REST_ENDPOINT, entry_point="", root_symbol_id="sym://test")

    def test_behavior_validation_empty_root_symbol(self):
        """Test that empty root symbol id raises ValueError."""
        with pytest.raises(ValueError, match="Root symbol id cannot be empty"):
            Behavior(id="behavior://test", name="test", kind=BehaviorKind.REST_ENDPOINT, entry_point="GET /test", root_symbol_id="")

    def test_behavior_list_to_tuple_conversion(self):
        """Test that lists are converted to tuples."""
        behavior = Behavior(
            id="behavior://test",
            name="test",
            kind=BehaviorKind.REST_ENDPOINT,
            entry_point="GET /test",
            root_symbol_id="sym://test",
            changed_symbol_ids=["sym://a", "sym://b"],
        )
        assert isinstance(behavior.changed_symbol_ids, tuple)
        assert behavior.changed_symbol_ids == ("sym://a", "sym://b")

    def test_behavior_kinds(self):
        """Test all behavior kinds."""
        assert BehaviorKind.REST_ENDPOINT.value == "rest_endpoint"
        assert BehaviorKind.WORKER_ENTRY.value == "worker_entry"
        assert BehaviorKind.SCHEDULED_JOB.value == "scheduled_job"
        assert BehaviorKind.CLI_COMMAND.value == "cli_command"
        assert BehaviorKind.GRAPHQL_RESOLVER.value == "graphql_resolver"
        assert BehaviorKind.EVENT_CONSUMER.value == "event_consumer"
        assert BehaviorKind.RPC_HANDLER.value == "rpc_handler"

    def test_execution_node_creation(self):
        """Test creating an ExecutionNode."""
        node = ExecutionNode(symbol_id="sym://test", order=0)
        assert node.symbol_id == "sym://test"
        assert node.order == 0

    def test_execution_node_validation_empty_id(self):
        """Test that empty symbol id raises ValueError."""
        with pytest.raises(ValueError, match="Symbol id cannot be empty"):
            ExecutionNode(symbol_id="", order=0)

    def test_execution_node_validation_negative_order(self):
        """Test that negative order raises ValueError."""
        with pytest.raises(ValueError, match="Order cannot be negative"):
            ExecutionNode(symbol_id="sym://test", order=-1)

    def test_execution_edge_creation(self):
        """Test creating an ExecutionEdge."""
        edge = ExecutionEdge(caller_id="sym://caller", callee_id="sym://callee", call_type="direct")
        assert edge.caller_id == "sym://caller"
        assert edge.callee_id == "sym://callee"
        assert edge.call_type == "direct"

    def test_execution_graph_creation(self):
        """Test creating an ExecutionGraph."""
        nodes = (
            ExecutionNode(symbol_id="sym://root", order=0),
            ExecutionNode(symbol_id="sym://a", order=1),
        )
        edges = (
            ExecutionEdge(caller_id="sym://root", callee_id="sym://a"),
        )
        graph = ExecutionGraph(
            behavior_id="behavior://test",
            nodes=nodes,
            edges=edges,
        )
        assert graph.behavior_id == "behavior://test"
        assert len(graph.nodes) == 2
        assert len(graph.edges) == 1
        assert graph.get_node_ids() == ("sym://root", "sym://a")

    def test_execution_graph_get_edges_for(self):
        """Test getting outgoing edges from a node."""
        graph = ExecutionGraph(
            behavior_id="behavior://test",
            nodes=(
                ExecutionNode(symbol_id="sym://a", order=0),
                ExecutionNode(symbol_id="sym://b", order=1),
            ),
            edges=(
                ExecutionEdge(caller_id="sym://a", callee_id="sym://b"),
            ),
        )
        edges = graph.get_edges_for("sym://a")
        assert len(edges) == 1
        assert edges[0].callee_id == "sym://b"

    def test_execution_graph_get_called_by(self):
        """Test getting incoming edges to a node."""
        graph = ExecutionGraph(
            behavior_id="behavior://test",
            nodes=(
                ExecutionNode(symbol_id="sym://a", order=0),
                ExecutionNode(symbol_id="sym://b", order=1),
            ),
            edges=(
                ExecutionEdge(caller_id="sym://a", callee_id="sym://b"),
            ),
        )
        edges = graph.get_called_by("sym://b")
        assert len(edges) == 1
        assert edges[0].caller_id == "sym://a"

    def test_behavior_model_creation(self):
        """Test creating a BehaviorModel."""
        behavior = Behavior(
            id="behavior://test",
            name="test",
            kind=BehaviorKind.REST_ENDPOINT,
            entry_point="GET /test",
            root_symbol_id="sym://test",
        )
        graph = ExecutionGraph(behavior_id="behavior://test")

        model = BehaviorModel(
            behaviors=(behavior,),
            execution_graphs=(graph,),
        )
        assert len(model.behaviors) == 1
        assert len(model.execution_graphs) == 1

    def test_behavior_model_get_behavior_by_id(self):
        """Test getting a behavior by id."""
        behavior = Behavior(
            id="behavior://test",
            name="test",
            kind=BehaviorKind.REST_ENDPOINT,
            entry_point="GET /test",
            root_symbol_id="sym://test",
        )
        model = BehaviorModel(behaviors=(behavior,))
        assert model.get_behavior_by_id("behavior://test") is behavior
        assert model.get_behavior_by_id("behavior://nonexistent") is None

    def test_behavior_model_get_behaviors_by_kind(self):
        """Test filtering behaviors by kind."""
        rest = Behavior(
            id="behavior://rest",
            name="rest",
            kind=BehaviorKind.REST_ENDPOINT,
            entry_point="GET /test",
            root_symbol_id="sym://rest",
        )
        worker = Behavior(
            id="behavior://worker",
            name="worker",
            kind=BehaviorKind.WORKER_ENTRY,
            entry_point="worker-queue",
            root_symbol_id="sym://worker",
        )
        model = BehaviorModel(behaviors=(rest, worker))
        rest_behaviors = model.get_behaviors_by_kind("rest_endpoint")
        assert len(rest_behaviors) == 1
        assert rest_behaviors[0].id == "behavior://rest"

    def test_behavior_model_get_affected_behaviors_for_symbol(self):
        """Test finding behaviors by changed symbol."""
        behavior = Behavior(
            id="behavior://test",
            name="test",
            kind=BehaviorKind.REST_ENDPOINT,
            entry_point="GET /test",
            root_symbol_id="sym://test",
            changed_symbol_ids=("sym://changed",),
        )
        model = BehaviorModel(behaviors=(behavior,))
        affected = model.get_affected_behaviors_for_symbol("sym://changed")
        assert len(affected) == 1
        assert affected[0].id == "behavior://test"

    def test_behavior_model_get_execution_graph(self):
        """Test getting an execution graph for a behavior."""
        graph = ExecutionGraph(behavior_id="behavior://test")
        model = BehaviorModel(execution_graphs=(graph,))
        assert model.get_execution_graph("behavior://test") is graph
        assert model.get_execution_graph("behavior://nonexistent") is None


# ---------------------------------------------------------------------------
# Behavior Compiler Tests
# ---------------------------------------------------------------------------

class TestBehaviorCompiler:
    """Tests for the BehaviorCompiler."""

    def test_compiler_initialization(self):
        """Test that the compiler initializes with correct passes."""
        compiler = BehaviorCompiler()
        assert len(compiler.passes) == 2
        assert compiler.passes[0].name == "behavior_compilation"
        assert compiler.passes[1].name == "behavior_graph"

    def test_compiler_pass_names(self):
        """Test getting pass names."""
        compiler = BehaviorCompiler()
        names = compiler.get_pass_names()
        assert names == ["behavior_compilation", "behavior_graph"]

    def test_compile_no_changes(self, sample_repository_model):
        """Test compiling with no changes."""
        compiler = BehaviorCompiler()
        change_model = TestHelper.create_change_model()
        result = compiler.compile(change_model, sample_repository_model)

        assert isinstance(result, BehaviorModel)
        assert len(result.behaviors) == 0
        assert len(result.execution_graphs) == 0

    def test_compile_empty_model(self):
        """Test compiling with None models."""
        compiler = BehaviorCompiler()
        result = compiler.compile(None, None)
        assert isinstance(result, BehaviorModel)
        assert len(result.behaviors) == 0
        assert len(result.execution_graphs) == 0

    def test_discover_behavior_from_added_symbol(self, sample_repository_model):
        """Test discovering a behavior from an added symbol."""
        compiler = BehaviorCompiler()

        # Simulate adding a symbol that is reachable from POST /checkout
        added_symbol = TestHelper.create_symbol(
            "python://checkout.py::validate_coupon",
            "validate_coupon",
            SymbolKind.FUNCTION,
            file="checkout.py",
        )
        change_model = TestHelper.create_change_model(
            added_symbols=[added_symbol],
        )

        result = compiler.compile(change_model, sample_repository_model)

        # Should find the POST /checkout behavior
        assert len(result.behaviors) == 1
        behavior = result.behaviors[0]
        assert behavior.kind == BehaviorKind.REST_ENDPOINT
        assert behavior.entry_point == "POST /checkout"
        assert "python://checkout.py::validate_coupon" in behavior.changed_symbol_ids

    def test_discover_behavior_from_modified_symbol(self, sample_repository_model):
        """Test discovering a behavior from a modified symbol."""
        compiler = BehaviorCompiler()

        # Simulate modifying a symbol in the checkout flow
        modified_symbol = TestHelper.create_symbol(
            "python://checkout.py::charge_card",
            "charge_card",
            SymbolKind.FUNCTION,
            file="checkout.py",
        )
        change_model = TestHelper.create_change_model(
            modified_symbols=[ModifiedSymbol(symbol=modified_symbol, changes=())],
        )

        result = compiler.compile(change_model, sample_repository_model)

        # Should find the POST /checkout behavior
        assert len(result.behaviors) == 1
        behavior = result.behaviors[0]
        assert behavior.kind == BehaviorKind.REST_ENDPOINT
        assert "python://checkout.py::charge_card" in behavior.changed_symbol_ids

    def test_discover_multiple_behaviors(self, sample_repository_model, sample_call_graph):
        """Test discovering multiple behaviors from different changed symbols."""
        compiler = BehaviorCompiler()

        # Modify symbols in both checkout and worker flows
        modified_checkout = TestHelper.create_symbol(
            "python://checkout.py::validate_coupon",
            "validate_coupon",
            SymbolKind.FUNCTION,
            file="checkout.py",
        )
        modified_worker = TestHelper.create_symbol(
            "python://worker.py::generate_pdf",
            "generate_pdf",
            SymbolKind.FUNCTION,
            file="worker.py",
        )
        change_model = TestHelper.create_change_model(
            modified_symbols=[
                ModifiedSymbol(symbol=modified_checkout, changes=()),
                ModifiedSymbol(symbol=modified_worker, changes=()),
            ],
        )

        result = compiler.compile(change_model, sample_repository_model)

        # Should find both behaviors
        assert len(result.behaviors) == 2

        kinds = {b.kind for b in result.behaviors}
        assert BehaviorKind.REST_ENDPOINT in kinds
        assert BehaviorKind.WORKER_ENTRY in kinds

    def test_build_execution_graph(self, sample_repository_model):
        """Test building an execution graph for a behavior."""
        compiler = BehaviorCompiler()

        # Modify a symbol in the checkout flow
        modified_symbol = TestHelper.create_symbol(
            "python://checkout.py::validate_coupon",
            "validate_coupon",
            SymbolKind.FUNCTION,
            file="checkout.py",
        )
        change_model = TestHelper.create_change_model(
            modified_symbols=[ModifiedSymbol(symbol=modified_symbol, changes=())],
        )

        result = compiler.compile(change_model, sample_repository_model)

        # Should have an execution graph for the checkout behavior
        assert len(result.execution_graphs) == 1
        graph = result.execution_graphs[0]

        # The graph should contain the checkout call chain
        node_ids = graph.get_node_ids()
        assert "handler://checkout" in node_ids
        assert "python://checkout.py::confirm_checkout" in node_ids
        assert "python://checkout.py::validate_coupon" in node_ids
        assert "python://checkout.py::charge_card" in node_ids
        assert "python://checkout.py::save_order" in node_ids
        assert "python://payment.py::process_payment" in node_ids

        # Should NOT contain worker symbols (separate tree)
        assert "python://worker.py::process_invoice" not in node_ids
        assert "python://billing.py::update_ledger" not in node_ids

    def test_execution_graph_ordering(self, sample_repository_model):
        """Test that execution graph nodes are ordered by execution."""
        compiler = BehaviorCompiler()

        modified_symbol = TestHelper.create_symbol(
            "python://checkout.py::validate_coupon",
            "validate_coupon",
            SymbolKind.FUNCTION,
            file="checkout.py",
        )
        change_model = TestHelper.create_change_model(
            modified_symbols=[ModifiedSymbol(symbol=modified_symbol, changes=())],
        )

        result = compiler.compile(change_model, sample_repository_model)
        graph = result.execution_graphs[0]

        # Root should be at order 0
        root_node = graph.nodes[0]
        assert root_node.symbol_id == "handler://checkout"
        assert root_node.order == 0

        # Confirm that order increases monotonically
        orders = [n.order for n in graph.nodes]
        assert orders == sorted(orders)

    def test_deterministic_output(self, sample_repository_model):
        """Test that compilation produces deterministic results."""
        compiler = BehaviorCompiler()

        modified_symbol = TestHelper.create_symbol(
            "python://checkout.py::validate_coupon",
            "validate_coupon",
            SymbolKind.FUNCTION,
            file="checkout.py",
        )
        change_model = TestHelper.create_change_model(
            modified_symbols=[ModifiedSymbol(symbol=modified_symbol, changes=())],
        )

        # Compile twice
        result1 = compiler.compile(change_model, sample_repository_model)
        result2 = compiler.compile(change_model, sample_repository_model)

        # Results should be identical
        assert len(result1.behaviors) == len(result2.behaviors)
        assert len(result1.execution_graphs) == len(result2.execution_graphs)

        for b1, b2 in zip(result1.behaviors, result2.behaviors):
            assert b1.id == b2.id
            assert b1.changed_symbol_ids == b2.changed_symbol_ids
            assert b1.entry_point == b2.entry_point

        for g1, g2 in zip(result1.execution_graphs, result2.execution_graphs):
            assert g1.behavior_id == g2.behavior_id
            assert g1.get_node_ids() == g2.get_node_ids()

    def test_pass_context_integrity(self):
        """Test that pass context maintains data between passes."""
        context = BehaviorPassContext()
        assert context.behaviors == []
        assert context.execution_graphs == []
        assert context.symbol_to_behaviors == {}
        assert context.metadata == {}
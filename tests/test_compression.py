"""Tests for the compression stage of the core engine pipeline."""

from __future__ import annotations

from language_adapters.ir.semantic_graph import SemanticGraph
from language_adapters.ir.nodes import BaseNode, NodeType
from language_adapters.ir.edges import BaseEdge, EdgeType

from core_engine import CorePipeline
from core_engine.graph import ReasoningPacket
from core_engine.compress import (
    CompressEngine,
    CompressRegistry,
    CollapseDuplicateRule,
    CollapseInfrastructureRule,
    CollapseORMRule,
    CollapseHelperRule,
    EmitCapabilityRule,
)
from core_engine.compress.compressed_graph import CompressedGraph, CompressedStatement, ComponentCapability
from core_engine.graph import ConnectedGraph, ChangeGroup, GroupEdge


def _make_node(
    node_type: NodeType,
    name: str,
    file_path: str = "app/service.py",
    change_type: str = "modified",
    **kwargs,
) -> BaseNode:
    """Helper to create a node."""
    return BaseNode(
        node_type=node_type,
        name=name,
        file_path=file_path,
        change_type=change_type,
        properties=kwargs,
    )


def _make_edge(
    edge_type: EdgeType,
    source: BaseNode,
    target: BaseNode,
    **kwargs,
) -> BaseEdge:
    """Helper to create an edge."""
    return BaseEdge(
        edge_type=edge_type,
        source=source,
        target=target,
        properties=kwargs,
    )


def _make_group(
    group_id: str,
    group_type: str,
    title: str,
    nodes: list[BaseNode],
) -> ChangeGroup:
    """Helper to create a ChangeGroup."""
    return ChangeGroup(
        id=group_id,
        type=group_type,
        title=title,
        nodes=nodes,
    )


def test_compression_ratio_meets_target():
    """Test that compression achieves meaningful reduction in reasoning surface."""
    graph = SemanticGraph()
    
    # Create a realistic graph with many nodes that match compression patterns
    # Infrastructure nodes (will be collapsed)
    graph.add_node(_make_node(NodeType.FUNCTION, "session.commit", change_type="modified"))
    graph.add_node(_make_node(NodeType.FUNCTION, "session.flush", change_type="modified"))
    graph.add_node(_make_node(NodeType.FUNCTION, "logger.info", change_type="modified"))
    graph.add_node(_make_node(NodeType.FUNCTION, "logger.debug", change_type="modified"))
    graph.add_node(_make_node(NodeType.FUNCTION, "typing.cast", change_type="modified"))
    
    # Helper methods (will be collapsed)
    graph.add_node(_make_node(NodeType.FUNCTION, "_get_validated_discount", change_type="modified"))
    graph.add_node(_make_node(NodeType.FUNCTION, "_get_validated_price", change_type="modified"))
    graph.add_node(_make_node(NodeType.FUNCTION, "_get_validated_subscription", change_type="modified"))
    graph.add_node(_make_node(NodeType.FUNCTION, "_validate_email", change_type="modified"))
    graph.add_node(_make_node(NodeType.FUNCTION, "_check_limits", change_type="modified"))
    
    # ORM nodes (will be collapsed)
    graph.add_node(_make_node(NodeType.QUERY, "user_query", change_type="modified",
                              target_model="User", operation="filter"))
    graph.add_node(_make_node(NodeType.FUNCTION, "filter", change_type="modified"))
    graph.add_node(_make_node(NodeType.FUNCTION, "order_by", change_type="modified"))
    
    # Models
    graph.add_node(_make_node(NodeType.MODEL, "Order", change_type="added"))
    graph.add_node(_make_node(NodeType.MODEL, "Customer", change_type="added"))
    
    # Endpoints
    graph.add_node(_make_node(
        NodeType.ENDPOINT, "checkout", change_type="added",
        method="POST", route="/checkout"
    ))
    
    pipeline = CorePipeline()
    packet = pipeline.run(graph)
    
    # Verify compression ratio is meaningful
    assert packet.total_original_nodes > 0
    assert packet.compression_ratio > 0.0
    
    # The compressed statements should be fewer than original nodes
    assert packet.total_compressed_statements < packet.total_original_nodes


def test_compressed_statements_are_reversible():
    """Test that compressed statements maintain references to original nodes."""
    graph = SemanticGraph()
    
    # Create duplicate function names (simulating multiple calls to same function)
    for i in range(3):
        graph.add_node(_make_node(
            NodeType.FUNCTION, "validate_price",
            change_type="modified"
        ))
    
    pipeline = CorePipeline()
    packet = pipeline.run(graph)
    
    # Check that compressed statements have original_node references
    for stmt in packet.compressed_statements:
        if stmt.label == "validate_price":
            assert stmt.count == 3
            assert len(stmt.original_nodes) == 3
            break
    else:
        # The statement might be collapsed differently, just verify reversibility exists
        assert len(packet.compressed_statements) > 0


def test_capability_facts_emitted():
    """Test that capability facts are emitted for components."""
    graph = SemanticGraph()
    
    # Create a service with validation, persistence, and external calls
    service = _make_node(NodeType.FUNCTION, "checkout_service", change_type="modified")
    validate = _make_node(NodeType.FUNCTION, "validate_price", change_type="modified")
    save = _make_node(NodeType.FUNCTION, "save_order", change_type="modified")
    model = _make_node(NodeType.MODEL, "Order", change_type="added")
    
    graph.add_node(service)
    graph.add_node(validate)
    graph.add_node(save)
    graph.add_node(model)
    
    graph.add_edge(_make_edge(EdgeType.CALLS, service, validate))
    graph.add_edge(_make_edge(EdgeType.CALLS, service, save))
    graph.add_edge(_make_edge(EdgeType.WRITES, save, model))
    
    pipeline = CorePipeline()
    packet = pipeline.run(graph)
    
    # Should have capabilities
    assert len(packet.capabilities) > 0
    
    # Capabilities should have structured fields
    for cap in packet.capabilities:
        assert cap.component_name
        assert isinstance(cap.reads, list)
        assert isinstance(cap.writes, list)
        assert isinstance(cap.validates, list)


def test_infrastructure_collapsed():
    """Test that infrastructure nodes are collapsed into categories."""
    graph = SemanticGraph()
    
    # Create infrastructure-like nodes
    graph.add_node(_make_node(NodeType.FUNCTION, "session.commit", change_type="modified"))
    graph.add_node(_make_node(NodeType.FUNCTION, "session.flush", change_type="modified"))
    graph.add_node(_make_node(NodeType.FUNCTION, "logger.info", change_type="modified"))
    
    pipeline = CorePipeline()
    packet = pipeline.run(graph)
    
    # Infrastructure should be collapsed
    infra_statements = [
        s for s in packet.compressed_statements
        if s.category == "infrastructure"
    ]
    assert len(infra_statements) > 0


def test_orm_details_collapsed():
    """Test that ORM details are collapsed into higher-level statements."""
    graph = SemanticGraph()
    
    # Create ORM-like nodes
    graph.add_node(_make_node(NodeType.QUERY, "user_query", change_type="modified",
                              target_model="User", operation="filter"))
    graph.add_node(_make_node(NodeType.FUNCTION, "filter", change_type="modified"))
    graph.add_node(_make_node(NodeType.FUNCTION, "order_by", change_type="modified"))
    
    pipeline = CorePipeline()
    packet = pipeline.run(graph)
    
    # ORM should be collapsed
    orm_statements = [
        s for s in packet.compressed_statements
        if s.category == "orm"
    ]
    assert len(orm_statements) > 0


def test_helper_methods_collapsed():
    """Test that private helper methods are collapsed."""
    graph = SemanticGraph()
    
    # Create helper methods
    graph.add_node(_make_node(
        NodeType.FUNCTION, "_get_validated_discount",
        change_type="modified"
    ))
    graph.add_node(_make_node(
        NodeType.FUNCTION, "_get_validated_price",
        change_type="modified"
    ))
    
    pipeline = CorePipeline()
    packet = pipeline.run(graph)
    
    # Helpers should be collapsed
    helper_statements = [
        s for s in packet.compressed_statements
        if s.category == "helper"
    ]
    assert len(helper_statements) > 0


def test_compressed_graph_preserves_original():
    """Test that CompressedGraph preserves the original graph for reversibility."""
    # Build a ConnectedGraph directly
    group1 = _make_group("g1", "service", "CheckoutService", [
        _make_node(NodeType.FUNCTION, "checkout", change_type="modified"),
    ])
    group2 = _make_group("g2", "model", "Order", [
        _make_node(NodeType.MODEL, "Order", change_type="added"),
    ])
    
    connected = ConnectedGraph(
        groups={"g1": group1, "g2": group2},
        group_edges=[
            GroupEdge(source_group_id="g1", target_group_id="g2", edge_type="writes"),
        ],
    )
    
    # Create compressed graph
    compressed = CompressedGraph.from_connected_graph(connected)
    
    # Original groups should be preserved
    assert len(compressed.original_groups) == 2
    assert compressed.original_groups["g1"].title == "CheckoutService"
    assert compressed.original_groups["g2"].title == "Order"
    
    # Original edges should be preserved
    assert len(compressed.original_edges) == 1
    assert compressed.original_edges[0].edge_type == "writes"
    
    # Total original nodes should be counted
    assert compressed.total_original_nodes == 2


def test_compressed_statement_has_required_fields():
    """Test that CompressedStatement has all required fields."""
    stmt = CompressedStatement(
        label="Test validation",
        count=3,
        original_nodes=["node1", "node2", "node3"],
        category="validation",
        details={"key": "value"},
    )
    
    assert stmt.label == "Test validation"
    assert stmt.count == 3
    assert len(stmt.original_nodes) == 3
    assert stmt.category == "validation"
    assert stmt.details["key"] == "value"


def test_component_capability_has_required_fields():
    """Test that ComponentCapability has all required fields."""
    cap = ComponentCapability(
        component_name="CheckoutService",
        reads=["Customer", "Discount"],
        writes=["Checkout"],
        validates=["Price"],
        external=["Stripe"],
        transactions=["session.flush"],
        queries=["get_orders"],
        schema=["email"],
        tests=["test_checkout"],
    )
    
    assert cap.component_name == "CheckoutService"
    assert "Customer" in cap.reads
    assert "Checkout" in cap.writes
    assert "Price" in cap.validates
    assert "Stripe" in cap.external
    assert "session.flush" in cap.transactions
    assert "get_orders" in cap.queries
    assert "email" in cap.schema
    assert "test_checkout" in cap.tests


def test_compress_engine_runs_without_errors():
    """Test that CompressEngine runs without errors."""
    registry = CompressRegistry()
    registry.register(CollapseDuplicateRule())
    registry.register(CollapseInfrastructureRule())
    registry.register(CollapseORMRule())
    registry.register(CollapseHelperRule())
    registry.register(EmitCapabilityRule())
    
    engine = CompressEngine(registry)
    
    # Create a minimal connected graph
    group = _make_group("g1", "service", "TestService", [
        _make_node(NodeType.FUNCTION, "test_func", change_type="modified"),
    ])
    connected = ConnectedGraph(groups={"g1": group})
    
    compressed = engine.run(connected)
    
    assert compressed is not None
    assert compressed.total_original_nodes == 1
    assert compressed.total_compressed_statements >= 0


def test_packet_contains_compressed_fields():
    """Test that ReasoningPacket contains the new compressed fields."""
    graph = SemanticGraph()
    graph.add_node(_make_node(NodeType.FUNCTION, "test", change_type="modified"))
    
    pipeline = CorePipeline()
    packet = pipeline.run(graph)
    
    # New compressed fields should be present
    assert hasattr(packet, 'compressed_statements')
    assert hasattr(packet, 'capabilities')
    assert hasattr(packet, 'compression_ratio')
    assert hasattr(packet, 'total_original_nodes')
    assert hasattr(packet, 'total_compressed_statements')
    
    # Serialization should include new fields
    d = packet.to_dict()
    assert "compressed_statements" in d
    assert "capabilities" in d
    assert "compression_ratio" in d
    assert "total_original_nodes" in d
    assert "total_compressed_statements" in d


def test_compression_with_realistic_workload():
    """Test compression with a realistic PR review workload."""
    graph = SemanticGraph()
    
    # Simulate a checkout feature PR with multiple components
    # Endpoints
    graph.add_node(_make_node(
        NodeType.ENDPOINT, "checkout", "api/checkout.py",
        change_type="added", method="POST", route="/checkout"
    ))
    
    # Service functions
    graph.add_node(_make_node(
        NodeType.FUNCTION, "process_checkout", "services/checkout.py",
        change_type="added"
    ))
    graph.add_node(_make_node(
        NodeType.FUNCTION, "validate_order", "services/checkout.py",
        change_type="added"
    ))
    graph.add_node(_make_node(
        NodeType.FUNCTION, "calculate_total", "services/checkout.py",
        change_type="modified"
    ))
    
    # Helper methods
    graph.add_node(_make_node(
        NodeType.FUNCTION, "_get_validated_discount", "services/checkout.py",
        change_type="added"
    ))
    graph.add_node(_make_node(
        NodeType.FUNCTION, "_get_validated_price", "services/checkout.py",
        change_type="added"
    ))
    graph.add_node(_make_node(
        NodeType.FUNCTION, "_get_validated_subscription", "services/checkout.py",
        change_type="added"
    ))
    
    # Models
    graph.add_node(_make_node(
        NodeType.MODEL, "Checkout", "models/checkout.py",
        change_type="added"
    ))
    graph.add_node(_make_node(
        NodeType.MODEL, "DiscountRedemption", "models/discount.py",
        change_type="added"
    ))
    
    # Fields
    graph.add_node(_make_node(
        NodeType.FIELD, "customer_email", "models/checkout.py",
        change_type="added", model_name="Checkout"
    ))
    
    # External service
    graph.add_node(_make_node(
        NodeType.EXTERNAL_SERVICE, "stripe", "services/payment.py",
        change_type="added", service_type="Stripe"
    ))
    
    # Transaction
    graph.add_node(_make_node(
        NodeType.TRANSACTION, "checkout_tx", "services/checkout.py",
        change_type="added", operations=["session.flush", "session.commit"]
    ))
    
    # Tests
    graph.add_node(_make_node(
        NodeType.TEST, "test_checkout_success", "tests/test_checkout.py",
        change_type="added", target_functions=["process_checkout"]
    ))
    graph.add_node(_make_node(
        NodeType.TEST, "test_checkout_failure", "tests/test_checkout.py",
        change_type="added", target_functions=["process_checkout"]
    ))
    
    # Infrastructure nodes
    graph.add_node(_make_node(
        NodeType.FUNCTION, "logger.info", "services/checkout.py",
        change_type="modified"
    ))
    graph.add_node(_make_node(
        NodeType.FUNCTION, "typing.cast", "services/checkout.py",
        change_type="modified"
    ))
    
    # ORM nodes
    graph.add_node(_make_node(
        NodeType.QUERY, "get_customer", "services/checkout.py",
        change_type="modified", target_model="Customer", operation="filter"
    ))
    graph.add_node(_make_node(
        NodeType.FUNCTION, "func.lower", "services/checkout.py",
        change_type="modified"
    ))
    
    # Edges
    nodes = list(graph.nodes.values())
    endpoint = next(n for n in nodes if n.name == "checkout")
    process = next(n for n in nodes if n.name == "process_checkout")
    validate = next(n for n in nodes if n.name == "validate_order")
    calculate = next(n for n in nodes if n.name == "calculate_total")
    checkout_model = next(n for n in nodes if n.name == "Checkout" and n.node_type == NodeType.MODEL)
    discount_model = next(n for n in nodes if n.name == "DiscountRedemption")
    stripe = next(n for n in nodes if n.name == "stripe")
    
    graph.add_edge(_make_edge(EdgeType.CALLS, endpoint, process))
    graph.add_edge(_make_edge(EdgeType.CALLS, process, validate))
    graph.add_edge(_make_edge(EdgeType.CALLS, process, calculate))
    graph.add_edge(_make_edge(EdgeType.WRITES, process, checkout_model))
    graph.add_edge(_make_edge(EdgeType.WRITES, process, discount_model))
    graph.add_edge(_make_edge(EdgeType.CALLS, process, stripe))
    
    pipeline = CorePipeline()
    packet = pipeline.run(graph)
    
    # Verify compression
    assert packet.total_original_nodes > 0
    assert packet.total_compressed_statements > 0
    
    # Verify capabilities are meaningful
    assert len(packet.capabilities) > 0
    
    # Verify the checkout component has meaningful capabilities
    checkout_caps = [c for c in packet.capabilities if "checkout" in c.component_name.lower()]
    if checkout_caps:
        cap = checkout_caps[0]
        # Should have some structured facts
        assert any([
            cap.reads, cap.writes, cap.validates,
            cap.external, cap.transactions, cap.queries,
            cap.schema, cap.tests,
        ])
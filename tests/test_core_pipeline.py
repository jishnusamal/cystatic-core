"""Tests for the core engine pipeline."""

from __future__ import annotations

import pytest

from language_adapters.ir.semantic_graph import SemanticGraph
from language_adapters.ir.nodes import BaseNode, NodeType, FunctionNode, MethodNode
from language_adapters.ir.edges import BaseEdge, EdgeType

from core_engine import CorePipeline
from core_engine.graph import ReasoningPacket


def _make_node(
    node_type: NodeType,
    name: str,
    file_path: str = "app/service.py",
    change_type: str = "modified",
    **kwargs,
) -> BaseNode:
    """Helper to create a node."""
    node = BaseNode(
        node_type=node_type,
        name=name,
        file_path=file_path,
        change_type=change_type,
        properties=kwargs,
    )
    return node


def _make_edge(
    edge_type: EdgeType,
    source: BaseNode,
    target: BaseNode,
    change_type: str = "added",
    **kwargs,
) -> BaseEdge:
    """Helper to create an edge."""
    return BaseEdge(
        edge_type=edge_type,
        source=source,
        target=target,
        change_type=change_type,
        properties=kwargs,
    )


def test_pipeline_runs():
    """Test that the pipeline runs without errors."""
    graph = SemanticGraph()
    
    endpoint = _make_node(NodeType.ENDPOINT, "create_user", change_type="added",
                          method="POST", route="/users")
    service = _make_node(NodeType.FUNCTION, "create_user_handler", change_type="added")
    repo = _make_node(NodeType.FUNCTION, "user_repository", change_type="added")
    model = _make_node(NodeType.MODEL, "User", change_type="added")
    
    graph.add_node(endpoint)
    graph.add_node(service)
    graph.add_node(repo)
    graph.add_node(model)
    
    graph.add_edge(_make_edge(EdgeType.CALLS, endpoint, service))
    graph.add_edge(_make_edge(EdgeType.CALLS, service, repo))
    graph.add_edge(_make_edge(EdgeType.WRITES, repo, model))
    
    pipeline = CorePipeline()
    packet = pipeline.run(graph)
    
    assert isinstance(packet, ReasoningPacket)
    assert len(packet.changed_areas) > 0
    assert len(packet.semantic_changes) > 0


def test_pipeline_produces_compact_output():
    """Test that the pipeline produces a compact representation."""
    graph = SemanticGraph()
    
    # Add multiple nodes
    for i in range(10):
        node = _make_node(NodeType.FUNCTION, f"func_{i}", change_type="modified")
        graph.add_node(node)
    
    pipeline = CorePipeline()
    packet = pipeline.run(graph)
    
    # Packet should be much smaller than raw graph
    assert isinstance(packet, ReasoningPacket)
    # The packet should have some structure
    assert isinstance(packet.changed_areas, list)
    assert isinstance(packet.semantic_changes, list)


def test_pipeline_groups_related_nodes():
    """Test that the pipeline groups related nodes."""
    graph = SemanticGraph()
    
    # Create endpoint and related service
    endpoint = _make_node(NodeType.ENDPOINT, "POST /users", "api/users.py",
                          change_type="added", method="POST", route="/users")
    handler = _make_node(NodeType.FUNCTION, "create_user", "services/user_service.py",
                         change_type="added")
    
    graph.add_node(endpoint)
    graph.add_node(handler)
    graph.add_edge(_make_edge(EdgeType.CALLS, endpoint, handler))
    
    pipeline = CorePipeline()
    packet = pipeline.run(graph)
    
    # Should have relationships
    assert isinstance(packet.relationships, list)


def test_pipeline_handles_empty_graph():
    """Test that the pipeline handles an empty graph."""
    graph = SemanticGraph()
    
    pipeline = CorePipeline()
    packet = pipeline.run(graph)
    
    assert isinstance(packet, ReasoningPacket)
    assert len(packet.changed_areas) == 0
    assert len(packet.semantic_changes) == 0


def test_pipeline_detects_migrations():
    """Test that the pipeline detects migrations."""
    graph = SemanticGraph()
    
    migration = _make_node(
        NodeType.MIGRATION,
        "add_role_column",
        "migrations/001.py",
        change_type="added",
        operations=[{"type": "add_column", "table": "users", "column": "role"}]
    )
    
    graph.add_node(migration)
    
    pipeline = CorePipeline()
    packet = pipeline.run(graph)
    
    assert len(packet.migrations) > 0
    assert any("add_column" in m for m in packet.migrations)


def test_pipeline_detects_tests():
    """Test that the pipeline detects tests."""
    graph = SemanticGraph()
    
    test = _make_node(
        NodeType.TEST,
        "test_create_user",
        "tests/test_users.py",
        change_type="added",
        target_functions=["create_user"]
    )
    
    graph.add_node(test)
    
    pipeline = CorePipeline()
    packet = pipeline.run(graph)
    
    assert len(packet.tests) > 0
    assert packet.tests[0]["name"] == "test_create_user"


def test_petwork_serialization():
    """Test that the packet can be serialized."""
    graph = SemanticGraph()
    
    endpoint = _make_node(NodeType.ENDPOINT, "test", change_type="added")
    graph.add_node(endpoint)
    
    pipeline = CorePipeline()
    packet = pipeline.run(graph)
    
    # Should be able to convert to dict
    d = packet.to_dict()
    assert isinstance(d, dict)
    assert "summary" in d
    assert "changed_areas" in d
    assert "semantic_changes" in d
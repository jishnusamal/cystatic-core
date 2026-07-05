"""Shared graph builder utilities — language-independent helpers for parsers."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from language_adapters.ir import (
    SemanticGraph,
    BaseNode,
    BaseEdge,
    NodeType,
    EdgeType,
    FunctionNode,
    MethodNode,
    ClassNode,
    ModuleNode,
    EndpointNode,
    ModelNode,
    FieldNode,
    QueryNode,
    TransactionNode,
    MigrationNode,
    TestNode,
    EventNode,
    ExternalServiceNode,
    CacheNode,
    QueueNode,
    CallsEdge,
    ReadsEdge,
    WritesEdge,
    CreatesEdge,
    UpdatesEdge,
    DeletesEdge,
    UsesEdge,
    ValidatesEdge,
    NormalizesEdge,
    TestsEdge,
    HasFieldEdge,
    ExposesEdge,
    PublishesEdge,
    SubscribesEdge,
    SendsHttpEdge,
    InheritsEdge,
    DecoratedByEdge,
)


class GraphBuilderUtils:
    """Utility methods for building semantic graphs from parsers."""

    @staticmethod
    def ensure_function(
        graph: SemanticGraph,
        name: str,
        file_path: str,
        **kwargs: Any,
    ) -> FunctionNode:
        """Get or create a FunctionNode."""
        existing = graph.get_node(NodeType.FUNCTION, name, file_path)
        if existing and isinstance(existing, FunctionNode):
            return existing
        node = FunctionNode(name=name, file_path=file_path, **kwargs)
        graph.add_node(node)
        return node

    @staticmethod
    def ensure_method(
        graph: SemanticGraph,
        name: str,
        file_path: str,
        class_name: str = "",
        **kwargs: Any,
    ) -> MethodNode:
        """Get or create a MethodNode."""
        existing = graph.get_node(NodeType.METHOD, name, file_path)
        if existing and isinstance(existing, MethodNode):
            return existing
        node = MethodNode(name=name, file_path=file_path, class_name=class_name, **kwargs)
        graph.add_node(node)
        return node

    @staticmethod
    def ensure_class(
        graph: SemanticGraph,
        name: str,
        file_path: str,
        **kwargs: Any,
    ) -> ClassNode:
        """Get or create a ClassNode."""
        existing = graph.get_node(NodeType.CLASS, name, file_path)
        if existing and isinstance(existing, ClassNode):
            return existing
        node = ClassNode(name=name, file_path=file_path, **kwargs)
        graph.add_node(node)
        return node

    @staticmethod
    def ensure_module(
        graph: SemanticGraph,
        file_path: str,
        **kwargs: Any,
    ) -> ModuleNode:
        """Get or create a ModuleNode."""
        existing = graph.get_node(NodeType.MODULE, file_path, file_path)
        if existing and isinstance(existing, ModuleNode):
            return existing
        node = ModuleNode(name=file_path, file_path=file_path, **kwargs)
        graph.add_node(node)
        return node

    @staticmethod
    def ensure_endpoint(
        graph: SemanticGraph,
        method: str,
        route: str,
        file_path: str,
        **kwargs: Any,
    ) -> EndpointNode:
        """Get or create an EndpointNode."""
        name = f"{method} {route}"
        existing = graph.get_node(NodeType.ENDPOINT, name, file_path)
        if existing and isinstance(existing, EndpointNode):
            return existing
        node = EndpointNode(name=name, file_path=file_path, method=method, route=route, **kwargs)
        graph.add_node(node)
        return node

    @staticmethod
    def ensure_model(
        graph: SemanticGraph,
        name: str,
        file_path: str,
        **kwargs: Any,
    ) -> ModelNode:
        """Get or create a ModelNode."""
        existing = graph.get_node(NodeType.MODEL, name, file_path)
        if existing and isinstance(existing, ModelNode):
            return existing
        node = ModelNode(name=name, file_path=file_path, **kwargs)
        graph.add_node(node)
        return node

    @staticmethod
    def ensure_field(
        graph: SemanticGraph,
        name: str,
        file_path: str,
        model_name: str = "",
        **kwargs: Any,
    ) -> FieldNode:
        """Get or create a FieldNode."""
        existing = graph.get_node(NodeType.FIELD, name, file_path)
        if existing and isinstance(existing, FieldNode):
            return existing
        node = FieldNode(name=name, file_path=file_path, model_name=model_name, **kwargs)
        graph.add_node(node)
        return node

    @staticmethod
    def ensure_query(
        graph: SemanticGraph,
        name: str,
        file_path: str,
        **kwargs: Any,
    ) -> QueryNode:
        """Get or create a QueryNode."""
        existing = graph.get_node(NodeType.QUERY, name, file_path)
        if existing and isinstance(existing, QueryNode):
            return existing
        node = QueryNode(name=name, file_path=file_path, **kwargs)
        graph.add_node(node)
        return node

    @staticmethod
    def add_calls(graph: SemanticGraph, caller: BaseNode, callee: BaseNode, **kwargs: Any) -> CallsEdge:
        """Add a CALLS edge between caller and callee."""
        edge = CallsEdge(source=caller, target=callee, **kwargs)
        graph.add_edge(edge)
        return edge

    @staticmethod
    def add_reads(graph: SemanticGraph, reader: BaseNode, target: BaseNode, **kwargs: Any) -> ReadsEdge:
        """Add a READS edge."""
        edge = ReadsEdge(source=reader, target=target, **kwargs)
        graph.add_edge(edge)
        return edge

    @staticmethod
    def add_writes(graph: SemanticGraph, writer: BaseNode, target: BaseNode, **kwargs: Any) -> WritesEdge:
        """Add a WRITES edge."""
        edge = WritesEdge(source=writer, target=target, **kwargs)
        graph.add_edge(edge)
        return edge

    @staticmethod
    def add_has_field(graph: SemanticGraph, model: BaseNode, field: BaseNode, **kwargs: Any) -> HasFieldEdge:
        """Add a HAS_FIELD edge."""
        edge = HasFieldEdge(source=model, target=field, **kwargs)
        graph.add_edge(edge)
        return edge

    @staticmethod
    def add_exposes(graph: SemanticGraph, endpoint: BaseNode, function: BaseNode, **kwargs: Any) -> ExposesEdge:
        """Add an EXPOSES edge."""
        edge = ExposesEdge(source=endpoint, target=function, **kwargs)
        graph.add_edge(edge)
        return edge
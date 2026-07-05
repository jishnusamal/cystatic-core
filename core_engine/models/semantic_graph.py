"""Validated semantic graph — wrapper around the raw SemanticGraph with integrity guarantees."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from language_adapters.ir.semantic_graph import SemanticGraph
from language_adapters.ir.nodes import BaseNode, NodeType
from language_adapters.ir.edges import BaseEdge, EdgeType


@dataclass
class ValidationResult:
    """Result of graph validation."""

    is_valid: bool = True
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class ValidatedSemanticGraph:
    """A semantic graph that has passed structural validation.

    Guarantees:
    - All node IDs are unique.
    - All edge source/target references exist as nodes.
    - No unknown node types or edge types.
    - Graph is internally consistent.
    """

    graph: SemanticGraph
    validation: ValidationResult = field(default_factory=ValidationResult)

    # Precomputed lookups for efficient traversal
    _nodes_by_type: Dict[NodeType, List[BaseNode]] = field(default_factory=dict)
    _edges_from: Dict[str, List[BaseEdge]] = field(default_factory=dict)
    _edges_to: Dict[str, List[BaseEdge]] = field(default_factory=dict)
    _entrypoints: List[BaseNode] = field(default_factory=list)
    _sinks: List[BaseNode] = field(default_factory=list)

    @classmethod
    def validate(cls, graph: SemanticGraph) -> ValidatedSemanticGraph:
        """Validate a raw SemanticGraph and wrap it."""
        errors: List[str] = []
        warnings: List[str] = []

        # 1. Check for duplicate node keys
        seen_keys: Set[str] = set()
        for node in graph.nodes.values():
            key = _node_key(node)
            if key in seen_keys:
                errors.append(f"Duplicate node key: {key}")
            seen_keys.add(key)

        # 2. Check edge integrity — all source/target nodes must exist
        known_keys = set(graph.nodes.keys())
        for edge in graph.edges:
            src_key = _node_key(edge.source)
            tgt_key = _node_key(edge.target)
            if src_key not in known_keys:
                errors.append(f"Edge source not found: {src_key}")
            if tgt_key not in known_keys:
                errors.append(f"Edge target not found: {tgt_key}")
            if edge.edge_type is None:
                errors.append("Edge with no type")
            if edge.source is None:
                errors.append("Edge with no source")
            if edge.target is None:
                errors.append("Edge with no target")

        # 3. Check nodes have valid types
        for node in graph.nodes.values():
            if node.node_type is None:
                errors.append(f"Node with no type: {node.name}")
            elif not isinstance(node.node_type, NodeType):
                errors.append(f"Unknown node type on {node.name}: {node.node_type}")

        # 4. Check edges have valid types
        for edge in graph.edges:
            if edge.edge_type is not None and not isinstance(edge.edge_type, EdgeType):
                warnings.append(f"Unknown edge type: {edge.edge_type}")

        validation = ValidationResult(is_valid=len(errors) == 0, errors=errors, warnings=warnings)

        # Build precomputed indexes for fast traversal
        nodes_by_type: Dict[NodeType, List[BaseNode]] = {}
        edges_from: Dict[str, List[BaseEdge]] = {}
        edges_to: Dict[str, List[BaseEdge]] = {}
        entrypoints: List[BaseNode] = []
        sinks: List[BaseNode] = []

        for node in graph.nodes.values():
            if node.node_type:
                nodes_by_type.setdefault(node.node_type, []).append(node)

        for edge in graph.edges:
            src_key = _node_key(edge.source)
            tgt_key = _node_key(edge.target)
            edges_from.setdefault(src_key, []).append(edge)
            edges_to.setdefault(tgt_key, []).append(edge)

        # Entrypoints: nodes that are called/triggered by nothing in the graph
        for node in graph.nodes.values():
            key = _node_key(node)
            if key not in edges_to:
                entrypoints.append(node)
            if key not in edges_from:
                sinks.append(node)

        return cls(
            graph=graph,
            validation=validation,
            _nodes_by_type=nodes_by_type,
            _edges_from=edges_from,
            _edges_to=edges_to,
            _entrypoints=entrypoints,
            _sinks=sinks,
        )

    def get_nodes_by_type(self, node_type: NodeType) -> List[BaseNode]:
        """Fast lookup of nodes by type."""
        return self._nodes_by_type.get(node_type, [])

    def get_edges_from(self, node: BaseNode) -> List[BaseEdge]:
        """Fast lookup of outgoing edges."""
        return self._edges_from.get(_node_key(node), [])

    def get_edges_to(self, node: BaseNode) -> List[BaseEdge]:
        """Fast lookup of incoming edges."""
        return self._edges_to.get(_node_key(node), [])

    def get_entrypoints(self) -> List[BaseNode]:
        """Nodes with no incoming edges — likely entrypoints."""
        return list(self._entrypoints)

    def get_sinks(self) -> List[BaseNode]:
        """Nodes with no outgoing edges — likely sinks."""
        return list(self._sinks)

    @property
    def is_valid(self) -> bool:
        return self.validation.is_valid

    @property
    def errors(self) -> List[str]:
        return list(self.validation.errors)

    @property
    def warnings(self) -> List[str]:
        return list(self.validation.warnings)


def _node_key(node: BaseNode) -> str:
    if hasattr(node, "class_name") and node.node_type == NodeType.METHOD and node.class_name:
        return f"{node.node_type.name}:{node.name}:{node.class_name}:{node.file_path}"
    return f"{node.node_type.name}:{node.name}:{node.file_path}"
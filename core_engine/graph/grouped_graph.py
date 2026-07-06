"""GroupedGraph - output of the Group stage."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from language_adapters.ir.nodes import BaseNode
from language_adapters.ir.edges import BaseEdge


@dataclass
class ChangeGroup:
    """A semantic group of related nodes."""
    
    id: str
    type: str
    title: str
    nodes: List[BaseNode] = field(default_factory=list)
    edges: List[BaseEdge] = field(default_factory=list)
    properties: Dict[str, Any] = field(default_factory=dict)


@dataclass
class GroupedGraph:
    """Output of the Group stage.
    
    Contains groups of related nodes instead of individual nodes.
    """
    
    groups: Dict[str, ChangeGroup] = field(default_factory=dict)
    ungrouped_nodes: Dict[str, BaseNode] = field(default_factory=dict)
    ungrouped_edges: List[BaseEdge] = field(default_factory=list)
    file_paths: List[str] = field(default_factory=list)
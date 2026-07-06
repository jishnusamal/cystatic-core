"""ConnectedGraph - output of the Connect stage."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from core_engine.graph import ChangeGroup


@dataclass
class GroupEdge:
    """Edge between two groups."""
    
    source_group_id: str
    target_group_id: str
    edge_type: str
    properties: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ConnectedGraph:
    """Output of the Connect stage.
    
    Contains groups with relationships between them.
    """
    
    groups: Dict[str, ChangeGroup] = field(default_factory=dict)
    group_edges: List[GroupEdge] = field(default_factory=list)
    file_paths: List[str] = field(default_factory=list)
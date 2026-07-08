"""Propagation models - downstream reachability."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass(frozen=True)
class PropagationPath:
    """A deterministic path from changed nodes to reachable nodes."""
    
    path_id: str
    source_node_id: str
    reachable_node_ids: List[str]
    reachable_edge_ids: List[str]
    path_type: str  # "shortest", "all", "models", "events", "workers", "apis"
    
    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "path_id": self.path_id,
            "source_node_id": self.source_node_id,
            "reachable_node_ids": self.reachable_node_ids,
            "reachable_edge_ids": self.reachable_edge_ids,
            "path_type": self.path_type,
        }
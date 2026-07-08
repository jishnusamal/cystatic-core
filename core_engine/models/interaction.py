"""Interaction models - structural interaction groups."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass(frozen=True)
class InteractionCluster:
    """A group of components that participate together."""
    
    cluster_id: str
    node_ids: List[str]
    cluster_type: str  # "scc", "articulation", "neighborhood", "connectivity"
    description: str
    
    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "cluster_id": self.cluster_id,
            "node_ids": self.node_ids,
            "cluster_type": self.cluster_type,
            "description": self.description,
        }
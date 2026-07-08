"""Execution models - executable structures."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass(frozen=True)
class ExecutionUnit:
    """An executable unit in the system."""
    
    unit_id: str
    unit_type: str  # "endpoint", "function", "transaction", "test", etc.
    name: str
    file_path: str
    node_ids: List[str] = field(default_factory=list)  # Graph nodes that form this unit
    change_type: str = "modified"
    
    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "unit_id": self.unit_id,
            "unit_type": self.unit_type,
            "name": self.name,
            "file_path": self.file_path,
            "node_ids": self.node_ids,
            "change_type": self.change_type,
        }
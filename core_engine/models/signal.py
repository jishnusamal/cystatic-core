"""Signal models - deterministic observations."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List


class SignalCategory(Enum):
    """Categories of signals."""
    EXECUTION = "execution"
    PERSISTENCE = "persistence"
    API = "api"
    EVENT = "event"
    SCHEMA = "schema"
    TRANSACTION = "transaction"
    MIGRATION = "migration"
    CACHE = "cache"
    AUTH = "auth"
    EXTERNAL = "external"
    CROSS_DOMAIN = "cross_domain"
    COVERAGE = "coverage"


@dataclass(frozen=True)
class Signal:
    """A deterministic observation from the graph."""
    
    signal_id: str
    name: str
    category: SignalCategory
    description: str
    rule_name: str
    node_ids: List[str] = field(default_factory=list)
    edge_ids: List[str] = field(default_factory=list)
    confidence: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "signal_id": self.signal_id,
            "name": self.name,
            "category": self.category.value,
            "description": self.description,
            "rule_name": self.rule_name,
            "node_ids": self.node_ids,
            "edge_ids": self.edge_ids,
            "confidence": self.confidence,
            "metadata": self.metadata,
        }
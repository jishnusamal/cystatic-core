"""
Constraint Layer — Phase 4

Structured system constraints extracted from static analysis + heuristics.
These constraints prevent LLM hallucinations by grounding reasoning in
observable system properties: idempotency, transaction boundaries,
retry semantics, external dependencies, schema versioning, etc.

Architecture:
  ConstraintExtractor -> list[Constraint] -> ConstraintSet
  ConstraintSet is serialized and fed to the LLM as ground truth.

Why this matters:
  Without constraints, the LLM guesses:
    "maybe duplicate order happens"
  With constraints, the LLM checks:
    "idempotency = not_guaranteed -> duplicate path valid"
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ConstraintType(str, Enum):
    """Categories of system constraints we extract."""
    IDEMPOTENCY = "idempotency"
    TRANSACTION_BOUNDARY = "transaction_boundary"
    RETRY_SEMANTICS = "retry_semantics"
    EXTERNAL_DEPENDENCY = "external_dependency"
    SCHEMA_VERSION = "schema_version"
    DATA_CONSISTENCY = "data_consistency"
    ORDERING_GUARANTEE = "ordering_guarantee"
    STATE_MANAGEMENT = "state_management"


class ConstraintValue(str, Enum):
    """Possible values for a constraint."""
    GUARANTEED = "guaranteed"
    NOT_GUARANTEED = "not_guaranteed"
    PARTIAL = "partial"
    UNKNOWN = "unknown"


class ConstraintSeverity(str, Enum):
    """How critical this constraint is for correctness."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class Constraint:
    """
    A single system constraint extracted from code analysis.

    Example:
        {
            "constraint": "order_creation",
            "type": "idempotency",
            "value": "not_guaranteed",
            "severity": "critical",
            "source": "_create_order_from_checkout",
            "evidence": "DB write without dedup check in order creation path",
            "file_path": "services/checkout.py"
        }
    """
    constraint: str
    type: ConstraintType
    value: ConstraintValue
    severity: ConstraintSeverity
    source: str
    evidence: str = ""
    file_path: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "constraint": self.constraint,
            "type": self.type.value,
            "value": self.value.value,
            "severity": self.severity.value,
            "source": self.source,
            "evidence": self.evidence,
            "file_path": self.file_path,
        }


@dataclass
class ConstraintSet:
    """
    Collection of constraints extracted from a PR analysis.
    Serialized and passed to the LLM to ground its reasoning.
    """
    constraints: list[Constraint] = field(default_factory=list)
    extraction_metadata: dict[str, Any] = field(default_factory=dict)

    def add(self, constraint: Constraint) -> None:
        self.constraints.append(constraint)

    def to_dict(self) -> dict[str, Any]:
        return {
            "constraints": [c.to_dict() for c in self.constraints],
            "total": len(self.constraints),
            "by_type": self._group_by_type(),
            "critical_count": sum(
                1 for c in self.constraints if c.severity == ConstraintSeverity.CRITICAL
            ),
            "metadata": self.extraction_metadata,
        }

    def _group_by_type(self) -> dict[str, list[dict[str, str]]]:
        grouped: dict[str, list[dict[str, str]]] = {}
        for c in self.constraints:
            type_key = c.type.value
            if type_key not in grouped:
                grouped[type_key] = []
            grouped[type_key].append({
                "constraint": c.constraint,
                "value": c.value.value,
            })
        return grouped

    def get_by_type(self, constraint_type: ConstraintType) -> list[Constraint]:
        return [c for c in self.constraints if c.type == constraint_type]

    def get_critical(self) -> list[Constraint]:
        return [c for c in self.constraints if c.severity == ConstraintSeverity.CRITICAL]

    def has_idempotency_gap(self) -> bool:
        """Check if any write operation lacks idempotency guarantees."""
        return any(
            c.type == ConstraintType.IDEMPOTENCY
            and c.value in (ConstraintValue.NOT_GUARANTEED, ConstraintValue.UNKNOWN)
            and c.severity in (ConstraintSeverity.CRITICAL, ConstraintSeverity.HIGH)
            for c in self.constraints
        )
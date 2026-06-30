"""
Constraint — a first-class model for system constraints detected by analyzers.

Replaces the generic ``dict[str, Any]`` placeholder in EvidenceBundle.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class Constraint(BaseModel):
    """A system constraint extracted from code analysis.

    Attributes:
        constraint: Short name for the constraint (e.g. "write_operation").
        constraint_type: Category of constraint (e.g. "idempotency", "transaction_boundary").
        value: The constraint value (e.g. "guaranteed", "not_guaranteed", "partial", "unknown").
        severity: How critical this constraint is for correctness.
        source: The function or symbol that triggered this constraint.
        evidence: Human-readable evidence supporting this constraint.
        file_path: Path to the source file.
    """
    constraint: str = Field(..., min_length=1)
    constraint_type: str = Field(..., min_length=1)
    value: str = Field(..., min_length=1)
    severity: str = Field(..., min_length=1)
    source: str = Field(default="unknown")
    evidence: str = Field(default="")
    file_path: str = Field(default="")
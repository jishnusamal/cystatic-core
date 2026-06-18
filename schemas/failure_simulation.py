"""
Schemas for the failure simulation pipeline.

Key changes from previous version:
- New verdicts: LOW_RISK, UNCERTAIN_IMPACT, NO_SIGNIFICANT_PROPAGATION_FOUND
- SAFE is no longer the default — it's a rare, strong verdict
- Added hop_confidence for causal chain confidence propagation
- Added failure_class (from templates) to scenarios
- Added system_behavior_deltas
"""
from typing import Literal
from pydantic import BaseModel, Field, field_validator, model_validator


class FailureScenario(BaseModel):
    """A single failure scenario with propagation confidence."""
    title: str = Field(min_length=8)
    trigger: str = Field(min_length=12)
    execution_path: str = Field(min_length=12)
    evidence_type: Literal["direct", "inferred", "structural_pattern", "inferred_bridge"] = "inferred"
    production_impact: str = Field(min_length=12)
    confidence: float = Field(ge=0.0, le=1.0)
    # NEW: Confidence propagation through causal chain
    hop_confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    causal_chain: str = ""  # "symbol → symbol → symbol" with confidence at each hop
    # NEW: Failure class from templates
    failure_class: str = ""  # "idempotency_break | double_charge_double_write | null_propagation | ..."
    # Existing fields
    first_observable_signal: str = "unknown"
    silent_failure: bool = True
    ci_would_catch: bool = False
    merge_risk_level: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"] = "MEDIUM"
    false_confidence_reason: str = ""
    why_it_slips_through: str = ""
    merge_confidence_trap: str = ""
    supported_by: list[str] = Field(default_factory=list)
    reasoning: str = ""


class FailureSimulationOutput(BaseModel):
    """Output from the failure simulation pipeline."""
    # NEW verdict system — SAFE is rare
    verdict: Literal[
        "SAFE",
        "LOW_RISK",
        "UNCERTAIN_IMPACT",
        "NO_SIGNIFICANT_PROPAGATION_FOUND",
        "REVIEW_REQUIRED",
        "BLOCK_REVIEW",
    ]
    failure_scenarios: list[FailureScenario] = Field(default_factory=list, max_length=5)
    hidden_impact_chain: list[str] = Field(default_factory=list)
    checked_risk_areas: list[str] = Field(default_factory=list)
    missing_critical_tests: list[str] = Field(default_factory=list)
    broken_assumptions: list[str] = Field(default_factory=list)
    silent_failure_summary: str = ""
    merge_risk_statement: str = ""
    verdict_rationale: str = ""
    final_question: str = ""
    # NEW: System behavior deltas (not just function-level diffs)
    system_behavior_deltas: list[dict] = Field(default_factory=list, max_length=5)
    # NEW: Matched failure templates
    matched_failure_templates: list[dict] = Field(default_factory=list)
    # NEW: Blast radius summary
    blast_radius: dict = Field(default_factory=dict)

    @field_validator("missing_critical_tests", "broken_assumptions", "hidden_impact_chain")
    @classmethod
    def no_empty_strings(cls, value):
        if any(not item.strip() for item in value):
            raise ValueError("List fields cannot contain empty strings")
        return value

    @model_validator(mode="after")
    def validate_by_verdict(self):
        # SAFE is rare — must have zero failure scenarios and strong rationale
        if self.verdict == "SAFE":
            if self.failure_scenarios:
                raise ValueError("SAFE verdict cannot have failure scenarios")
            if not self.verdict_rationale or len(self.verdict_rationale.strip()) < 20:
                raise ValueError("SAFE verdict requires strong rationale (>= 20 chars)")
            return self

        # LOW_RISK: minor concerns, no critical paths
        if self.verdict == "LOW_RISK":
            if not self.verdict_rationale or len(self.verdict_rationale.strip()) < 12:
                raise ValueError("LOW_RISK verdict requires rationale")
            return self

        # UNCERTAIN_IMPACT: suspicions but no direct evidence
        if self.verdict == "UNCERTAIN_IMPACT":
            if not self.final_question or len(self.final_question.strip()) < 10:
                raise ValueError("UNCERTAIN_IMPACT requires a meaningful final question")
            return self

        # NO_SIGNIFICANT_PROPAGATION_FOUND: changes exist but no downstream impact detected
        if self.verdict == "NO_SIGNIFICANT_PROPAGATION_FOUND":
            return self

        # REVIEW_REQUIRED and BLOCK_REVIEW require scenarios
        if self.verdict in ("REVIEW_REQUIRED", "BLOCK_REVIEW"):
            if not self.failure_scenarios:
                raise ValueError(f"{self.verdict} requires at least one failure scenario")
            if not self.final_question or len(self.final_question.strip()) < 12:
                raise ValueError(f"{self.verdict} requires meaningful final_question")
            for scenario in self.failure_scenarios:
                if scenario.confidence < 0.6:
                    raise ValueError(f"{self.verdict} failure scenarios require confidence >= 0.6")

        return self
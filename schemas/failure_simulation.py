"""
Schemas for the failure simulation pipeline.

Key changes from previous version:
- New verdicts: LOW_RISK, UNCERTAIN_IMPACT, NO_SIGNIFICANT_PROPAGATION_FOUND
- SAFE is no longer the default — it's a rare, strong verdict
- Added failure_class (from templates) to scenarios
- Added system_behavior_deltas
- NEW: LLM as validator/ranker/explainer (hybrid deterministic + LLM architecture)
"""
from typing import Literal
from pydantic import BaseModel, Field, field_validator, model_validator


class FailureScenario(BaseModel):
    """A single failure scenario."""
    title: str = Field(min_length=8)
    trigger: str = Field(min_length=12)
    evidence_type: Literal["direct", "inferred", "structural_pattern", "inferred_bridge"] = "inferred"
    production_impact: str = Field(min_length=12)
    confidence: float = Field(ge=0.0, le=1.0)
    causal_chain: str = ""  # "symbol → symbol → symbol"
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


# ══════════════════════════════════════════════════════════════════════════════
# NEW: LLM Validation & Ranking Models
# ══════════════════════════════════════════════════════════════════════════════

class ScenarioValidation(BaseModel):
    """LLM validation of a single deterministic scenario.
    
    The LLM acts as an expert reviewer, validating the deterministic engine's
    hypotheses rather than generating new ones from scratch.
    """
    scenario_title: str = Field(min_length=1)
    verdict: Literal["VALIDATE", "DOWNGRADE", "REJECT", "NEEDS_MORE_EVIDENCE"]
    confidence_calibration: str = Field(min_length=10)  # "0.84 is well-calibrated because..."
    production_symptom: str = Field(min_length=20)  # First observable signal in production
    ci_catch_probability: Literal["HIGH", "MEDIUM", "LOW", "NONE"]
    strongest_evidence: str = Field(min_length=10)
    weakest_evidence: str = Field(min_length=10)
    additional_evidence_needed: list[str] = Field(default_factory=list, max_length=5)
    reasoning: str = Field(min_length=20)  # Why this verdict


class ScenarioRanking(BaseModel):
    """LLM ranking of a scenario by production risk."""
    rank: int = Field(ge=1, le=10)
    scenario_title: str = Field(min_length=1)
    production_risk_score: float = Field(ge=0.0, le=1.0)
    risk_factors: list[str] = Field(default_factory=list, max_length=5)
    user_facing_impact: str = Field(min_length=10)


class EvidenceChallenge(BaseModel):
    """LLM challenge to deterministic engine's evidence."""
    scenario_title: str = Field(min_length=1)
    assumption: str = Field(min_length=10)  # "Assumes runtime call path exists"
    weakness: str = Field(min_length=10)  # "No evidence of actual invocation"
    missing_evidence: str = Field(min_length=10)  # "Would need call graph to confirm"
    confidence_if_validated: float = Field(ge=0.0, le=1.0)  # What confidence would be if evidence existed


class ImpactExplanation(BaseModel):
    """LLM explanation of architectural impact."""
    scenario_title: str = Field(min_length=1)
    explanation: str = Field(min_length=50)  # Architectural reasoning
    affected_systems: list[str] = Field(default_factory=list, max_length=10)
    blast_radius: str = Field(min_length=20)  # "Checkout → Invoice → Wallet"


class TopRisk(BaseModel):
    """Top risk with LLM reasoning."""
    rank: int = Field(ge=1, le=5)
    title: str = Field(min_length=8)
    confidence: float = Field(ge=0.0, le=1.0)
    validation_verdict: Literal["VALIDATE", "DOWNGRADE", "REJECT", "NEEDS_MORE_EVIDENCE"]
    production_symptom: str = Field(min_length=20)
    why_it_matters: str = Field(min_length=30)  # Architectural reasoning
    evidence_quality: Literal["STRONG", "MODERATE", "WEAK"]
    recommended_action: str = Field(min_length=10)


# ══════════════════════════════════════════════════════════════════════════════
# Main Output Schema
# ══════════════════════════════════════════════════════════════════════════════

class FailureSimulationOutput(BaseModel):
    """Output from the failure simulation pipeline.
    
    Hybrid architecture:
    - Deterministic engine: fact generator (evidence, hypotheses, scenarios)
    - LLM: expert reviewer (validates, ranks, explains, challenges)
    """
    # NEW verdict system — SAFE is rare
    verdict: Literal[
        "SAFE",
        "LOW_RISK",
        "UNCERTAIN_IMPACT",
        "NO_SIGNIFICANT_PROPAGATION_FOUND",
        "REVIEW_REQUIRED",
        "BLOCK_REVIEW",
    ]
    
    # Deterministic scenarios (from compression pipeline)
    failure_scenarios: list[FailureScenario] = Field(default_factory=list, max_length=5)
    
    # NEW: LLM validation of each scenario
    scenario_validations: list[ScenarioValidation] = Field(default_factory=list, max_length=5)
    
    # NEW: LLM ranking by production risk
    scenario_rankings: list[ScenarioRanking] = Field(default_factory=list, max_length=5)
    
    # NEW: LLM challenges to weak evidence
    evidence_challenges: list[EvidenceChallenge] = Field(default_factory=list, max_length=10)
    
    # NEW: What evidence would increase confidence
    missing_evidence: list[str] = Field(default_factory=list, max_length=10)
    
    # NEW: Architectural explanations
    impact_explanations: list[ImpactExplanation] = Field(default_factory=list, max_length=5)
    
    # NEW: Final engineering report
    executive_summary: str = Field(default="")
    top_risks: list[TopRisk] = Field(default_factory=list, max_length=5)
    
    # Existing fields
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

    @field_validator("missing_critical_tests", "broken_assumptions", "hidden_impact_chain", "missing_evidence")
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

        # REVIEW_REQUIRED and BLOCK_REVIEW: require either scenarios OR substantive review output
        if self.verdict in ("REVIEW_REQUIRED", "BLOCK_REVIEW"):
            # Enforce field-level length constraints for substantive output
            if not self.failure_scenarios:
                # Check executive_summary length if provided
                if self.executive_summary and len(self.executive_summary.strip()) < 50:
                    raise ValueError("executive_summary must be at least 50 characters when provided")
                # Check verdict_rationale length if provided
                if self.verdict_rationale and len(self.verdict_rationale.strip()) < 20:
                    raise ValueError("verdict_rationale must be at least 20 characters when provided")
                
                # Check if we have substantive review output
                has_substantive_output = (
                    (self.executive_summary and len(self.executive_summary.strip()) >= 50)
                    or (self.verdict_rationale and len(self.verdict_rationale.strip()) >= 20)
                    or self.top_risks
                    or self.scenario_validations
                    or self.impact_explanations
                )
                
                if not has_substantive_output:
                    raise ValueError(
                        f"{self.verdict} requires either failure scenarios or substantive review output "
                        f"(executive_summary, verdict_rationale, top_risks, scenario_validations, or impact_explanations)"
                    )
                # Valid: LLM provided review without generating scenarios
                return self
            
            # If scenarios exist, require final_question and validate confidence
            if not self.final_question or len(self.final_question.strip()) < 12:
                raise ValueError(f"{self.verdict} requires meaningful final_question")
            for scenario in self.failure_scenarios:
                if scenario.confidence < 0.6:
                    raise ValueError(f"{self.verdict} failure scenarios require confidence >= 0.6")

        return self

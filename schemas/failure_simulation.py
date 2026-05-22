from typing import Literal
from pydantic import BaseModel, Field, field_validator, model_validator


class FailureScenario(BaseModel):
    title: str = Field(min_length=8)
    trigger: str = Field(min_length=12)
    execution_path: str = Field(min_length=12)
    evidence_type: Literal["direct", "inferred", "structural_pattern"] = "inferred"
    production_impact: str = Field(min_length=12)
    confidence: float = Field(ge=0.0, le=1.0)
    first_observable_signal: str = "unknown"
    silent_failure: bool = True
    ci_would_catch: bool = False
    merge_risk_level: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"] = "MEDIUM"


class FailureSimulationOutput(BaseModel):
    failure_scenarios: list[FailureScenario] = Field(default_factory=list, max_length=3)
    hidden_impact_chain: list[str] = Field(default_factory=list)
    checked_risk_areas: list[str] = Field(default_factory=list)
    missing_critical_tests: list[str] = Field(default_factory=list)
    broken_assumptions: list[str] = Field(default_factory=list)
    silent_failure_summary: str = ""
    merge_risk_statement: str = ""
    verdict_rationale: str = ""
    verdict: Literal["SAFE", "REVIEW_REQUIRED", "BLOCK_REVIEW"]
    final_question: str = ""

    @field_validator("missing_critical_tests", "broken_assumptions", "hidden_impact_chain")
    @classmethod
    def no_empty_strings(cls, value):
        if any(not item.strip() for item in value):
            raise ValueError("List fields cannot contain empty strings")
        return value

    @model_validator(mode="after")
    def validate_by_verdict(self):
        if self.verdict == "SAFE":
            return self

        if not self.failure_scenarios:
            raise ValueError("Non-SAFE verdict requires at least one failure scenario")

        if not self.final_question or len(self.final_question.strip()) < 12:
            raise ValueError("Non-SAFE verdict requires meaningful final_question")

        for scenario in self.failure_scenarios:
            if scenario.confidence < 0.6:
                raise ValueError("Non-SAFE failure scenarios require confidence >= 0.6")

        return self
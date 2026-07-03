"""
Schemas for the failure simulation pipeline.

Key design rule:
    If this schema were displayed directly in the Factor UI without an LLM,
    would it still make sense to an experienced engineer?

    If yes, we've found the right abstraction level.

The output schema exposes only reviewer-ready content — not internal
implementation artifacts like scenarios, evidence clusters, or hypotheses.
"""
from typing import Literal
from pydantic import BaseModel, Field, field_validator, model_validator


class PrimaryConcern(BaseModel):
    """The single highest-confidence production risk."""
    title: str = Field(min_length=8)
    why_blocking: str = Field(min_length=20)
    execution_path: str = Field(default="N/A", min_length=3)
    customer_or_business_impact: str = Field(min_length=20)
    why_existing_tests_miss_it: str = Field(min_length=20)
    confidence_rationale: str = Field(min_length=20)
    required_validation: str = Field(min_length=10)


class AdditionalObservation(BaseModel):
    """A secondary observation. Only include if genuinely useful."""
    title: str = Field(min_length=8)
    observation: str = Field(min_length=20)
    symbols: list[str] = Field(default_factory=list)


# ══════════════════════════════════════════════════════════════════════════════
# Main Output Schema
# ══════════════════════════════════════════════════════════════════════════════

class FailureSimulationOutput(BaseModel):
    """Output from the failure simulation pipeline.

    This is a reviewer-ready output. The LLM transforms deterministic
    findings into a credible engineering review.

    The output schema mirrors what a senior engineer would write,
    not what the internal analysis engine produced.
    """
    # Verdict
    verdict: Literal[
        "APPROVE",
        "REVIEW_REQUIRED",
        "BLOCK",
    ]

    # Executive summary (max 120 words)
    executive_summary: str = Field(
        default="",
        description="No more than 120 words. Synthesizes the single most important finding.",
    )

    # Primary concern — the single highest-confidence production risk
    primary_concern: PrimaryConcern | None = None

    # Additional observations — only if genuinely useful
    additional_observations: list[AdditionalObservation] = Field(
        default_factory=list,
        max_length=3,
        description="Maximum three additional observations. Omit if none add meaningful value.",
    )

    # Required tests
    required_tests: list[str] = Field(
        default_factory=list,
        max_length=5,
    )

    # Reviewer questions
    reviewer_questions: list[str] = Field(
        default_factory=list,
        max_length=5,
    )

    # Merge recommendation (plain string)
    merge_recommendation: str = Field(
        default="",
        description="One-sentence merge recommendation.",
    )

    @field_validator("required_tests", "reviewer_questions")
    @classmethod
    def no_empty_strings(cls, value):
        if any(not item.strip() for item in value):
            raise ValueError("List fields cannot contain empty strings")
        return value

    @model_validator(mode="after")
    def validate_by_verdict(self):
        # BLOCK: requires primary concern
        if self.verdict == "BLOCK":
            if not self.primary_concern:
                raise ValueError("BLOCK verdict requires a primary_concern")
            if not self.executive_summary or len(self.executive_summary.strip()) < 30:
                raise ValueError("BLOCK verdict requires executive_summary (>= 30 chars)")
            return self

        # REVIEW_REQUIRED: requires either primary concern or executive summary
        if self.verdict == "REVIEW_REQUIRED":
            has_substantive_output = (
                (self.executive_summary and len(self.executive_summary.strip()) >= 30)
                or self.primary_concern is not None
                or self.additional_observations
            )
            if not has_substantive_output:
                raise ValueError(
                    "REVIEW_REQUIRED requires either executive_summary, "
                    "primary_concern, or additional_observations"
                )
            return self

        # APPROVE: requires positive assessment
        if self.verdict == "APPROVE":
            if not self.executive_summary or len(self.executive_summary.strip()) < 30:
                raise ValueError("APPROVE verdict requires executive_summary (>= 30 chars)")
            return self

        return self
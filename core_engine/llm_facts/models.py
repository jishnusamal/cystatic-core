"""
LlmFacts models — the deterministic engine's output to the LLM.

These models represent facts, not conclusions. The LLM receives these
facts and reasons from them, rather than receiving pre-compressed
conclusions that it can only rephrase.

Design rule: If these facts were displayed directly in the Factor UI
without an LLM, would an experienced engineer immediately understand
what changed and what to look for? If yes, the abstraction is correct.
"""
from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class ChangedSymbolFact(BaseModel):
    """A symbol that was changed in the PR.

    Attributes:
        symbol: The bare symbol name (e.g., redeem_discount).
        qualified_name: Fully qualified name (e.g., module.ClassName.method).
        kind: Kind of symbol (function, method, class, etc.).
        file_path: File where the symbol lives.
        module: Module or package.
        domain: Business domain.
    """
    symbol: str = Field(..., min_length=1)
    qualified_name: str | None = None
    kind: str = "function"
    file_path: str = ""
    module: str | None = None
    domain: str | None = None


class BehaviorChange(BaseModel):
    """A deterministic behavior change observation.

    These are facts about what changed, not conclusions about impact.

    Attributes:
        type: Type of change (validation, persistence, migration, transaction,
              query, event, api, model, test).
        symbol: The symbol or entity where the change occurred.
        change: What actually changed (e.g., "customer_email added to validation").
        detail: Additional detail about the change.
    """
    type: str = Field(..., min_length=1)
    symbol: str = ""
    change: str = Field(..., min_length=1)
    detail: str = ""


class Relationship(BaseModel):
    """A deterministic relationship between two entities.

    These are facts about the codebase structure, not predictions.

    Attributes:
        from_symbol: The source entity.
        to_symbol: The target entity.
        relationship_type: Type of relationship (calls, writes, reads,
                          inherits, implements, references, etc.).
        detail: Additional detail about the relationship.
    """
    from_symbol: str = Field(..., min_length=1)
    to_symbol: str = Field(..., min_length=1)
    relationship_type: str = "references"
    detail: str = ""


class TestCoverage(BaseModel):
    """Test coverage information for the changed code.

    Attributes:
        test_name: Name of the test.
        covers: What the test covers (list of symbols, domains, or behaviors).
        test_file: File path of the test.
    """
    test_name: str = Field(..., min_length=1)
    covers: list[str] = Field(default_factory=list)
    test_file: str = ""


class MigrationFact(BaseModel):
    """A database migration fact.

    Attributes:
        table: The table being migrated.
        added_columns: Columns being added.
        nullable: Whether the new columns are nullable.
        backfilled: Whether existing rows have been backfilled.
        detail: Additional detail about the migration.
    """
    table: str = ""
    added_columns: list[str] = Field(default_factory=list)
    nullable: bool = True
    backfilled: bool = False
    detail: str = ""


class ReviewHint(BaseModel):
    """A deterministic observation that may warrant reviewer attention.

    These are NOT conclusions. They are prompts for investigation.

    Examples:
        - "validation logic moved"
        - "new nullable persistence fields"
        - "read-before-write pattern"
        - "email normalization added"
        - "transaction boundary modified"
        - "migration without backfill"
        - "new uniqueness criteria"
    """
    hint: str = Field(..., min_length=1)


class ArchitecturalPath(BaseModel):
    """An architectural execution path.

    Attributes:
        path: Ordered list of symbols in the path.
        description: What this path represents.
    """
    path: list[str] = Field(default_factory=list)
    description: str = ""


class LlmFacts(BaseModel):
    """Complete set of deterministic facts for the LLM.

    This is the ONLY data the LLM receives. It contains facts, not conclusions.
    The LLM reasons from these facts to produce its review.

    Attributes:
        repo: Repository name.
        pr_number: PR number.
        changed_symbols: All symbols changed in the PR.
        behavior_changes: Deterministic behavior change observations.
        relationships: Deterministic relationships between entities.
        test_coverage: Existing test coverage information.
        missing_coverage: Symbols or paths with no test coverage.
        migrations: Database migration facts.
        review_hints: Deterministic observations for reviewer attention.
        architectural_paths: Key architectural execution paths.
    """
    repo: str = ""
    pr_number: int = 0

    changed_symbols: list[ChangedSymbolFact] = Field(default_factory=list)
    behavior_changes: list[BehaviorChange] = Field(default_factory=list)
    relationships: list[Relationship] = Field(default_factory=list)

    test_coverage: list[TestCoverage] = Field(default_factory=list)
    missing_coverage: list[str] = Field(default_factory=list)

    migrations: list[MigrationFact] = Field(default_factory=list)
    review_hints: list[ReviewHint] = Field(default_factory=list)
    architectural_paths: list[ArchitecturalPath] = Field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return self.model_dump()
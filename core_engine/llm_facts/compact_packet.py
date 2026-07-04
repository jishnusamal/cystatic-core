"""
CompactPacket — the redesigned, information-dense feature packet for LLM input.

Design principles:
  1. Transmit facts, not conclusions.
  2. Prefer structured data over prose.
  3. Avoid duplicated information.
  4. Compress aggressively.

Target size: ≤2,000 input tokens (ideal: 1,200–1,800 tokens) for typical PRs.
"""
from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class SymbolEntry(BaseModel):
    """A single entry in the symbol table.

    Attributes:
        id: Numeric identifier referenced by other sections.
        k: Kind of symbol (fn, method, class, route, etc.).
        n: Bare symbol name (e.g., redeem_discount).
    """
    id: int = Field(..., ge=1)
    k: str = Field(..., min_length=1)
    n: str = Field(..., min_length=1)


class FeatureFlags(BaseModel):
    """Bitfield-like flags for behavior changes.

    Each flag is 0 or 1. The prompt documents what each flag means.
    Only flags that are 1 are included.

    Attributes:
        validation_change: Validation logic was modified.
        normalization: Normalization logic was added/modified.
        persistence_change: Persistence logic was modified.
        transaction_change: Transaction boundary was modified.
        migration: A database migration was added.
        query_change: A query was modified.
        event_change: An event was added/modified.
        api_change: An API endpoint was modified.
        model_change: A model/schema was modified.
        constraint_change: A constraint was added/modified.
    """
    validation_change: int = 0
    normalization: int = 0
    persistence_change: int = 0
    transaction_change: int = 0
    migration: int = 0
    query_change: int = 0
    event_change: int = 0
    api_change: int = 0
    model_change: int = 0
    constraint_change: int = 0


class RelationEdge(BaseModel):
    """A graph edge between two symbols.

    Attributes:
        from_id: Source symbol ID (references SymbolEntry.id).
        to_id: Target symbol ID (references SymbolEntry.id).
        t: Relationship type (calls, writes, reads, inherits, etc.).
    """
    from_id: int = Field(..., ge=1)
    to_id: int = Field(..., ge=1)
    t: str = Field(..., min_length=1)


class ExecutionPathSummary(BaseModel):
    """Compressed summary of execution paths.

    Attributes:
        entrypoints: Symbol IDs of entry points.
        affected_sinks: Symbol IDs of affected sinks.
        max_depth: Maximum propagation depth.
    """
    entrypoints: list[int] = Field(default_factory=list)
    affected_sinks: list[int] = Field(default_factory=list)
    max_depth: int = 0


class CoverageSummary(BaseModel):
    """Aggregated test coverage information.

    Attributes:
        unit: Number of unit tests.
        integration: Number of integration tests.
        e2e: Number of end-to-end tests.
        covered: Capabilities with test coverage.
        missing: Capabilities without test coverage.
    """
    unit: int = 0
    integration: int = 0
    e2e: int = 0
    covered: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)


class MigrationSummary(BaseModel):
    """Compressed migration metadata.

    Attributes:
        table: The table being migrated.
        cols: Number of columns added.
        nullable: Whether new columns are nullable.
        backfill: Whether existing rows have been backfilled.
    """
    table: str = ""
    cols: int = 0
    nullable: bool = True
    backfill: bool = False


class ArchitectureDelta(BaseModel):
    """Only changed graph properties.

    Attributes:
        new_reads: Symbol IDs of newly read entities.
        new_writes: Symbol IDs of newly written entities.
        changed_calls: Pairs of symbol IDs for changed call relationships.
    """
    new_reads: list[int] = Field(default_factory=list)
    new_writes: list[int] = Field(default_factory=list)
    changed_calls: list[list[int]] = Field(default_factory=list)


class ConfidenceComponents(BaseModel):
    """Confidence split into components.

    Attributes:
        overall: Overall confidence (0.0–1.0).
        causal: Confidence in causal analysis.
        reachability: Confidence in reachability analysis.
        coverage: Confidence in test coverage analysis.
    """
    overall: float = 0.0
    causal: float = 0.0
    reachability: float = 0.0
    coverage: float = 0.0


class CompactPacket(BaseModel):
    """The redesigned compact feature packet for LLM input.

    This is the ONLY data the LLM receives. It contains facts, not conclusions.
    The LLM reasons from these facts to produce its review.

    Attributes:
        summary: Quantitative summary metrics.
        symbols: Symbol table (index of all referenced symbols).
        features: Feature flags for behavior changes.
        relations: Graph edges between symbols.
        coverage: Aggregated test coverage.
        migrations: Compressed migration metadata.
        hints: Enumerated review signals.
        architecture: Changed graph properties.
        confidence: Confidence split into components.
    """
    summary: dict[str, int] = Field(default_factory=dict)
    symbols: list[SymbolEntry] = Field(default_factory=list)
    features: FeatureFlags = Field(default_factory=FeatureFlags)
    relations: list[RelationEdge] = Field(default_factory=list)
    execution: ExecutionPathSummary = Field(default_factory=ExecutionPathSummary)
    coverage: CoverageSummary = Field(default_factory=CoverageSummary)
    migrations: list[MigrationSummary] = Field(default_factory=list)
    hints: list[str] = Field(default_factory=list)
    architecture: ArchitectureDelta = Field(default_factory=ArchitectureDelta)
    confidence: ConfidenceComponents = Field(default_factory=ConfidenceComponents)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return self.model_dump(exclude_none=True)
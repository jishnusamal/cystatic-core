"""
LLM Facts — the deterministic engine stops one layer earlier.

Produces a CompactPacket — a compact, structured feature packet (~1.2k–1.8k tokens)
where every token contributes meaningful engineering context.

Design principles:
  1. Transmit facts, not conclusions.
  2. Prefer structured data over prose.
  3. Avoid duplicated information.
  4. Compress aggressively.
"""
from __future__ import annotations

from .models import (
    LlmFacts,
    ChangedSymbolFact,
    BehaviorChange,
    Relationship,
    TestCoverage,
    MigrationFact,
    ReviewHint,
    ArchitecturalPath,
)
from .builder import LlmFactsBuilder
from .reviewer_facts_builder import ReviewerFactsBuilder
from .compact_packet import (
    CompactPacket,
    SymbolEntry,
    FeatureFlags,
    RelationEdge,
    ExecutionPathSummary,
    CoverageSummary,
    MigrationSummary,
    ArchitectureDelta,
    ConfidenceComponents,
)

__all__ = [
    "LlmFacts",
    "ChangedSymbolFact",
    "BehaviorChange",
    "Relationship",
    "TestCoverage",
    "MigrationFact",
    "ReviewHint",
    "ArchitecturalPath",
    "LlmFactsBuilder",
    "ReviewerFactsBuilder",
    "CompactPacket",
    "SymbolEntry",
    "FeatureFlags",
    "RelationEdge",
    "ExecutionPathSummary",
    "CoverageSummary",
    "MigrationSummary",
    "ArchitectureDelta",
    "ConfidenceComponents",
]

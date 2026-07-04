"""
ReviewerFactsBuilder — deterministic compression layer between LlmFacts and the LLM.

This builder consumes LlmFacts and emits a CompactPacket — a compact, structured
feature packet (~1.2k–1.8k tokens) where every token contributes meaningful
engineering context.

Design principles:
  1. Transmit facts, not conclusions.
  2. Prefer structured data over prose.
  3. Avoid duplicated information.
  4. Compress aggressively.

Usage:
    builder = ReviewerFactsBuilder(llm_facts)
    packet = builder.build()
"""
from __future__ import annotations

from typing import Any
from collections import Counter, defaultdict

from .models import LlmFacts
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


# ── Budget limits ──────────────────────────────────────────────────────────

_SYMBOL_LIMIT = 40
_RELATION_LIMIT = 40
_MIGRATION_LIMIT = 5
_HINT_LIMIT = 10
_COVERED_LIMIT = 10
_MISSING_LIMIT = 10


class ReviewerFactsBuilder:
    """Deterministic compression layer between LlmFacts and the LLM.

    Consumes LlmFacts and emits a CompactPacket — a compact, structured
    feature packet with symbol IDs, feature flags, graph edges, and
    compressed summaries.
    """

    def __init__(
        self,
        llm_facts: LlmFacts,
        repo: str = "",
        pr_number: int = 0,
    ):
        self._facts = llm_facts
        self._repo = repo or llm_facts.repo
        self._pr_number = pr_number or llm_facts.pr_number
        # Symbol table: name -> id
        self._symbol_map: dict[str, int] = {}
        # Reverse: id -> (kind, name)
        self._symbols_by_id: dict[int, tuple[str, str]] = {}
        self._next_id = 1

    def build(self) -> CompactPacket:
        """Build the compact reviewer packet.

        Returns:
            A CompactPacket with only reviewer-relevant fields.
        """
        # Build symbol table first (all other sections reference IDs)
        self._build_symbol_table()

        packet = CompactPacket(
            summary=self._build_summary(),
            symbols=self._build_symbol_list(),
            features=self._build_features(),
            relations=self._build_relations(),
            execution=self._build_execution_paths(),
            coverage=self._build_coverage(),
            migrations=self._build_migrations(),
            hints=self._build_hints(),
            architecture=self._build_architecture_delta(),
            confidence=self._compute_confidence(),
        )

        return packet

    # ── Symbol Table ──────────────────────────────────────────────────────

    def _get_or_create_id(self, name: str, kind: str = "fn") -> int:
        """Get or create a symbol ID for the given name."""
        if name in self._symbol_map:
            return self._symbol_map[name]
        sid = self._next_id
        self._next_id += 1
        self._symbol_map[name] = sid
        self._symbols_by_id[sid] = (kind, name)
        return sid

    def _build_symbol_table(self) -> None:
        """Build the symbol table from changed symbols and relationships."""
        # Add all changed symbols
        for cs in self._facts.changed_symbols:
            name = cs.symbol
            kind = (cs.kind or "fn").lower()
            # Skip test symbols and private helpers
            if name.startswith("test_") or name.startswith("Test"):
                continue
            if name.startswith("_") and not name.startswith("__"):
                continue
            if cs.file_path and "test" in cs.file_path.lower():
                continue
            self._get_or_create_id(name, kind)

        # Add symbols from relationships
        for r in self._facts.relationships:
            if r.from_symbol:
                self._get_or_create_id(r.from_symbol, "fn")
            if r.to_symbol:
                self._get_or_create_id(r.to_symbol, "fn")

        # Add symbols from architectural paths
        for ap in self._facts.architectural_paths:
            for s in ap.path:
                if s and not s.startswith("_") and not s.startswith("test_"):
                    self._get_or_create_id(s, "fn")

    def _build_symbol_list(self) -> list[SymbolEntry]:
        """Build the symbol list, respecting budget limits."""
        symbols = [
            SymbolEntry(id=sid, k=kind, n=name)
            for sid, (kind, name) in sorted(self._symbols_by_id.items())
        ]
        # Enforce budget
        if len(symbols) > _SYMBOL_LIMIT:
            symbols = symbols[:_SYMBOL_LIMIT]
        return symbols

    # ── Summary ───────────────────────────────────────────────────────────

    def _build_summary(self) -> dict[str, int]:
        """Build compact quantitative summary."""
        facts = self._facts
        files: set[str] = set()
        for cs in facts.changed_symbols:
            if not cs.file_path:
                continue
            # Skip test files (matches symbol table filtering)
            if "test" in cs.file_path.lower():
                continue
            files.add(cs.file_path)

        # Count risk patterns from hints
        risk_patterns = len(facts.review_hints)

        return {
            "files": len(files),
            "symbols": len(self._symbol_map),
            "entrypoints": self._count_entrypoints(),
            "risk_patterns": risk_patterns,
            "tests": len(facts.test_coverage),
            "migrations": len(facts.migrations),
        }

    def _count_entrypoints(self) -> int:
        """Count entrypoint symbols."""
        count = 0
        for cs in self._facts.changed_symbols:
            kind = (cs.kind or "").lower()
            if kind in ("route", "endpoint", "handler", "view", "controller", "api"):
                count += 1
        return count

    # ── Feature Flags ─────────────────────────────────────────────────────

    def _build_features(self) -> FeatureFlags:
        """Build feature flags from behavior changes."""
        flags = FeatureFlags()

        for bc in self._facts.behavior_changes:
            change_type = bc.type.lower()
            change_text = (bc.change + " " + bc.detail).lower()

            if change_type == "validation":
                flags.validation_change = 1
            if change_type == "persistence":
                flags.persistence_change = 1
            if change_type == "transaction":
                flags.transaction_change = 1
            if change_type == "migration":
                flags.migration = 1
            if change_type == "query":
                flags.query_change = 1
            if change_type == "event":
                flags.event_change = 1
            if change_type == "api":
                flags.api_change = 1
            if change_type == "model":
                flags.model_change = 1
            if change_type == "constraint":
                flags.constraint_change = 1

            # Detect normalization from change text
            if "normaliz" in change_text or "normalis" in change_text:
                flags.normalization = 1

        return flags

    # ── Relations (graph edges) ───────────────────────────────────────────

    def _build_relations(self) -> list[RelationEdge]:
        """Build graph edges from relationships, respecting budget."""
        edges: list[RelationEdge] = []
        seen: set[tuple[int, int, str]] = set()

        for r in self._facts.relationships:
            from_id = self._symbol_map.get(r.from_symbol)
            to_id = self._symbol_map.get(r.to_symbol)
            if from_id is None or to_id is None:
                continue

            rel_type = r.relationship_type.lower()
            # Normalize relationship type
            if rel_type in ("writes", "write", "persist", "save"):
                rel_type = "writes"
            elif rel_type in ("reads", "read", "query", "select"):
                rel_type = "reads"
            elif rel_type in ("calls", "call"):
                rel_type = "calls"
            elif rel_type in ("inherits", "extends", "implements"):
                rel_type = "inherits"
            elif rel_type in ("import", "imports"):
                rel_type = "imports"
            elif rel_type in ("event", "publish", "subscribe", "emits_event"):
                rel_type = "emits_event"
            elif rel_type in ("transaction", "shared_transaction", "shares_transaction"):
                rel_type = "shares_transaction"
            elif rel_type in ("crosses_domain", "crosses_service"):
                rel_type = "crosses"
            elif rel_type in ("references", "depends_on"):
                rel_type = "refs"

            key = (from_id, to_id, rel_type)
            if key in seen:
                continue
            seen.add(key)

            edges.append(RelationEdge(
                from_id=from_id,
                to_id=to_id,
                t=rel_type,
            ))

        # Enforce budget: keep highest-value edges (calls > writes > reads)
        if len(edges) > _RELATION_LIMIT:
            priority = {"calls": 0, "writes": 1, "reads": 2, "inherits": 3,
                        "imports": 4, "emits_event": 5, "shares_transaction": 6,
                        "crosses": 7, "refs": 8}
            edges.sort(key=lambda e: priority.get(e.t, 99))
            edges = edges[:_RELATION_LIMIT]

        return edges

    # ── Execution Paths (compressed) ──────────────────────────────────────

    def _build_execution_paths(self) -> ExecutionPathSummary:
        """Build compressed execution path summary."""
        entrypoints: set[int] = set()
        affected_sinks: set[int] = set()
        max_depth = 0

        for ap in self._facts.architectural_paths:
            if not ap.path:
                continue

            # Compress: remove internal/private symbols
            compressed = [
                s for s in ap.path
                if not s.startswith("_") and not s.startswith("test_")
            ]
            if len(compressed) < 2:
                continue

            # First symbol is entrypoint
            first = compressed[0]
            if first in self._symbol_map:
                entrypoints.add(self._symbol_map[first])

            # Last symbol is sink
            last = compressed[-1]
            if last in self._symbol_map:
                affected_sinks.add(self._symbol_map[last])

            # Track depth
            depth = len(compressed)
            if depth > max_depth:
                max_depth = depth

        return ExecutionPathSummary(
            entrypoints=sorted(entrypoints),
            affected_sinks=sorted(affected_sinks),
            max_depth=max_depth,
        )

    # ── Coverage ──────────────────────────────────────────────────────────

    def _build_coverage(self) -> CoverageSummary:
        """Build aggregated test coverage summary."""
        unit = 0
        integration = 0
        e2e = 0
        covered_caps: set[str] = set()
        missing_caps: set[str] = set()

        # Count tests by type
        for tc in self._facts.test_coverage:
            name_lower = tc.test_name.lower()
            if "e2e" in name_lower or "end_to_end" in name_lower:
                e2e += 1
            elif "integration" in name_lower:
                integration += 1
            else:
                unit += 1

            # Collect covered capabilities
            for cover in tc.covers:
                covered_caps.add(cover)

        # Collect missing coverage
        for mc in self._facts.missing_coverage:
            missing_caps.add(mc)

        # Enforce budget
        covered_list = sorted(covered_caps)[:_COVERED_LIMIT]
        missing_list = sorted(missing_caps)[:_MISSING_LIMIT]

        return CoverageSummary(
            unit=unit,
            integration=integration,
            e2e=e2e,
            covered=covered_list,
            missing=missing_list,
        )

    # ── Migrations ────────────────────────────────────────────────────────

    def _build_migrations(self) -> list[MigrationSummary]:
        """Build compressed migration metadata."""
        migrations: list[MigrationSummary] = []

        for m in self._facts.migrations:
            migrations.append(MigrationSummary(
                table=m.table or "unknown",
                cols=len(m.added_columns),
                nullable=m.nullable,
                backfill=m.backfilled,
            ))

        # Enforce budget
        if len(migrations) > _MIGRATION_LIMIT:
            migrations = migrations[:_MIGRATION_LIMIT]

        return migrations

    # ── Hints (enumerated signals) ────────────────────────────────────────

    def _build_hints(self) -> list[str]:
        """Build enumerated review signals."""
        hints: list[str] = []
        seen: set[str] = set()

        for rh in self._facts.review_hints:
            hint = rh.hint.strip()
            if not hint or hint in seen:
                continue
            seen.add(hint)

            # Normalize to enumerated signal format
            normalized = hint.lower().replace(" ", "_").replace(":", "")
            hints.append(normalized)

        # Enforce budget
        if len(hints) > _HINT_LIMIT:
            hints = hints[:_HINT_LIMIT]

        return hints

    # ── Architecture Delta ────────────────────────────────────────────────

    def _build_architecture_delta(self) -> ArchitectureDelta:
        """Build only changed graph properties."""
        new_reads: set[int] = set()
        new_writes: set[int] = set()
        changed_calls: list[list[int]] = []

        for r in self._facts.relationships:
            from_id = self._symbol_map.get(r.from_symbol)
            to_id = self._symbol_map.get(r.to_symbol)
            if from_id is None or to_id is None:
                continue

            rel_type = r.relationship_type.lower()
            if rel_type in ("writes", "write", "persist", "save"):
                new_writes.add(to_id)
            elif rel_type in ("reads", "read", "query", "select"):
                new_reads.add(to_id)
            elif rel_type in ("calls", "call"):
                changed_calls.append([from_id, to_id])

        return ArchitectureDelta(
            new_reads=sorted(new_reads),
            new_writes=sorted(new_writes),
            changed_calls=changed_calls,
        )

    # ── Confidence ────────────────────────────────────────────────────────

    def _compute_confidence(self) -> ConfidenceComponents:
        """Compute confidence split into components."""
        facts = self._facts

        # Overall: based on presence of key facts
        overall = 1.0
        if not facts.changed_symbols:
            overall *= 0.3
        if not facts.behavior_changes:
            overall *= 0.6
        if not facts.relationships:
            overall *= 0.7
        if not facts.architectural_paths:
            overall *= 0.8

        # Causal: confidence in causal analysis
        causal = 1.0
        if not facts.behavior_changes:
            causal *= 0.5
        if not facts.relationships:
            causal *= 0.6

        # Reachability: confidence in reachability analysis
        reachability = 1.0
        if not facts.architectural_paths:
            reachability *= 0.4
        if not facts.relationships:
            reachability *= 0.7

        # Coverage: confidence in test coverage analysis
        coverage = 1.0
        if not facts.test_coverage:
            coverage *= 0.5
        if not facts.missing_coverage:
            coverage *= 0.8

        return ConfidenceComponents(
            overall=round(overall, 3),
            causal=round(causal, 3),
            reachability=round(reachability, 3),
            coverage=round(coverage, 3),
        )
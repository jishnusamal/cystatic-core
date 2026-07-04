"""
LlmFactsBuilder — extracts raw facts from the deterministic engine.

This builder is the ONLY interface between the deterministic engine and the LLM.
It extracts facts (not conclusions) from the EvidenceBundle and ChangeUnderstanding.

The builder answers only:
  - What changed?
  - Where did it change?
  - What relationships exist?
  - What tests exist?
  - What migrations exist?
  - What review hints exist?

It does NOT produce:
  - Scenarios
  - Hypotheses
  - Canonical risks
  - Failure classes
  - Operational impact
  - Business domain conclusions
"""
from __future__ import annotations

from typing import Any

from core_engine.models.evidence_bundle import EvidenceBundle
from core_engine.models.change_understanding import ChangeUnderstanding
from core_engine.models.enums import EvidenceType

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


class LlmFactsBuilder:
    """Builds LlmFacts from deterministic engine outputs.

    This builder extracts facts from EvidenceBundle and ChangeUnderstanding.
    It does NOT access inference results, hypotheses, scenarios, or any
    other conclusion-producing pipeline stage.
    """

    @staticmethod
    def build(
        bundle: EvidenceBundle,
        understanding: ChangeUnderstanding | None = None,
        repo: str = "",
        pr_number: int = 0,
    ) -> LlmFacts:
        """Build LlmFacts from deterministic engine outputs.

        Args:
            bundle: EvidenceBundle from EvidencePipeline.
            understanding: Optional ChangeUnderstanding for enriched file data.
            repo: Repository name.
            pr_number: PR number.

        Returns:
            LlmFacts containing only deterministic facts.
        """
        facts = LlmFacts(
            repo=repo,
            pr_number=pr_number,
        )

        # ── What changed? ────────────────────────────────────────────────
        facts.changed_symbols = LlmFactsBuilder._extract_changed_symbols(bundle)

        # ── Behavior changes ─────────────────────────────────────────────
        facts.behavior_changes = LlmFactsBuilder._extract_behavior_changes(
            bundle, understanding
        )

        # ── Relationships ────────────────────────────────────────────────
        facts.relationships = LlmFactsBuilder._extract_relationships(bundle)

        # ── Test coverage ────────────────────────────────────────────────
        facts.test_coverage = LlmFactsBuilder._extract_test_coverage(
            bundle, understanding
        )
        facts.missing_coverage = LlmFactsBuilder._extract_missing_coverage(
            bundle, understanding
        )

        # ── Migrations ───────────────────────────────────────────────────
        facts.migrations = LlmFactsBuilder._extract_migrations(
            bundle, understanding
        )

        # ── Review hints ─────────────────────────────────────────────────
        facts.review_hints = LlmFactsBuilder._extract_review_hints(
            bundle, understanding
        )

        # ── Architectural paths ──────────────────────────────────────────
        facts.architectural_paths = LlmFactsBuilder._extract_architectural_paths(
            bundle, understanding
        )

        return facts

    @staticmethod
    def _extract_changed_symbols(
        bundle: EvidenceBundle,
    ) -> list[ChangedSymbolFact]:
        """Extract changed symbols from the evidence bundle."""
        symbols: list[ChangedSymbolFact] = []
        seen: set[str] = set()

        for cs in bundle.changed_symbols:
            name = cs.symbol if hasattr(cs, "symbol") else ""
            if not name or name in seen:
                continue
            seen.add(name)

            symbols.append(ChangedSymbolFact(
                symbol=name,
                qualified_name=getattr(cs, "qualified_name", None),
                kind=getattr(cs, "kind", "function"),
                file_path=getattr(cs, "file_path", ""),
                module=getattr(cs, "module", None),
                domain=getattr(cs, "domain", None),
            ))

        return symbols

    @staticmethod
    def _extract_behavior_changes(
        bundle: EvidenceBundle,
        understanding: ChangeUnderstanding | None,
    ) -> list[BehaviorChange]:
        """Extract behavior changes from evidence.

        Looks at impact evidence to determine what actually changed:
        - validation changes
        - persistence changes
        - transaction changes
        - query changes
        - event changes
        - API changes
        - model changes
        """
        changes: list[BehaviorChange] = []
        seen: set[str] = set()

        # Extract from impact evidence
        for ev in bundle.impact_evidence:
            try:
                source = ev.source.name if hasattr(ev.source, "name") else str(ev.source)
                target = ev.target.name if hasattr(ev.target, "name") else str(ev.target)
                evidence_type = ev.evidence_type
                if hasattr(evidence_type, "value"):
                    evidence_type = evidence_type.value
                evidence_type = str(evidence_type)

                # Map evidence types to behavior change types
                change_type = LlmFactsBuilder._map_evidence_to_change_type(evidence_type)
                if not change_type:
                    continue

                change_desc = f"{source} → {target}: {ev.explanation}" if ev.explanation else f"{source} → {target}"

                key = f"{change_type}:{source}:{target}"
                if key in seen:
                    continue
                seen.add(key)

                changes.append(BehaviorChange(
                    type=change_type,
                    symbol=source,
                    change=change_desc,
                    detail=ev.explanation or "",
                ))
            except Exception:
                continue

        # Extract from constraints
        for c in bundle.constraints:
            try:
                symbol = c.symbol if hasattr(c, "symbol") else ""
                constraint_type = c.constraint_type if hasattr(c, "constraint_type") else ""
                description = c.description if hasattr(c, "description") else ""

                if not symbol or not constraint_type:
                    continue

                key = f"constraint:{symbol}:{constraint_type}"
                if key in seen:
                    continue
                seen.add(key)

                changes.append(BehaviorChange(
                    type="constraint",
                    symbol=symbol,
                    change=f"{constraint_type} constraint on {symbol}",
                    detail=description,
                ))
            except Exception:
                continue

        # Extract from side effects
        for se in bundle.side_effects:
            try:
                symbol = se.symbol if hasattr(se, "symbol") else ""
                effect_type = se.effect_type if hasattr(se, "effect_type") else ""
                description = se.description if hasattr(se, "description") else ""

                if not symbol:
                    continue

                if hasattr(effect_type, "value"):
                    effect_type = effect_type.value
                effect_type = str(effect_type)

                key = f"side_effect:{symbol}:{effect_type}"
                if key in seen:
                    continue
                seen.add(key)

                changes.append(BehaviorChange(
                    type="side_effect",
                    symbol=symbol,
                    change=f"{symbol} has {effect_type} side effect",
                    detail=description,
                ))
            except Exception:
                continue

        return changes

    @staticmethod
    def _map_evidence_to_change_type(evidence_type: str) -> str | None:
        """Map evidence type to behavior change type."""
        et = evidence_type.lower()

        # Transaction changes
        if any(t in et for t in ("transaction", "starts_transaction", "commits_transaction",
                                  "rolls_back_transaction", "inside_transaction", "shared_transaction")):
            return "transaction"

        # Persistence changes
        if any(t in et for t in ("persistence", "database", "db_", "table", "column",
                                  "migration", "schema")):
            return "persistence"

        # Query changes
        if any(t in et for t in ("query", "sql", "select", "filter", "aggregate")):
            return "query"

        # Event changes
        if any(t in et for t in ("event", "publish", "subscribe", "webhook", "callback")):
            return "event"

        # API changes
        if any(t in et for t in ("api", "endpoint", "route", "http", "rest")):
            return "api"

        # Model changes
        if any(t in et for t in ("model", "entity", "dto", "schema")):
            return "model"

        # Validation changes
        if any(t in et for t in ("validation", "constraint", "check", "guard", "assert")):
            return "validation"

        # Service/domain changes
        if any(t in et for t in ("service", "domain", "cross_domain", "shared")):
            return "service"

        return None

    @staticmethod
    def _extract_relationships(
        bundle: EvidenceBundle,
    ) -> list[Relationship]:
        """Extract relationships from impact evidence.

        Produces facts like:
          - redeem_discount() calls is_redeemable_discount()
          - redeem_discount() writes DiscountRedemption
          - CheckoutService.confirm() calls redeem_discount()
        """
        relationships: list[Relationship] = []
        seen: set[str] = set()

        for ev in bundle.impact_evidence:
            try:
                source = ev.source.name if hasattr(ev.source, "name") else str(ev.source)
                target = ev.target.name if hasattr(ev.target, "name") else str(ev.target)
                evidence_type = ev.evidence_type
                if hasattr(evidence_type, "value"):
                    evidence_type = evidence_type.value
                evidence_type = str(evidence_type)

                # Map evidence type to relationship type
                rel_type = LlmFactsBuilder._map_evidence_to_relationship_type(evidence_type)
                if not rel_type:
                    continue

                key = f"{source}:{rel_type}:{target}"
                if key in seen:
                    continue
                seen.add(key)

                relationships.append(Relationship(
                    from_symbol=source,
                    to_symbol=target,
                    relationship_type=rel_type,
                    detail=ev.explanation or "",
                ))
            except Exception:
                continue

        return relationships

    @staticmethod
    def _map_evidence_to_relationship_type(evidence_type: str) -> str | None:
        """Map evidence type to relationship type."""
        et = evidence_type.lower()

        if "calls" in et or "call" in et:
            return "calls"
        if "writes" in et or "write" in et or "persist" in et or "save" in et:
            return "writes"
        if "reads" in et or "read" in et or "query" in et or "select" in et:
            return "reads"
        if "inherits" in et or "extends" in et or "implements" in et:
            return "inherits"
        if "import" in et:
            return "imports"
        if "event" in et or "publish" in et or "subscribe" in et:
            return "emits_event"
        if "transaction" in et or "shared_transaction" in et:
            return "shares_transaction"
        if "domain" in et or "cross_domain" in et:
            return "crosses_domain"
        if "service" in et:
            return "crosses_service"
        if "reference" in et or "ref" in et:
            return "references"
        if "dependency" in et or "depends" in et:
            return "depends_on"

        return None

    @staticmethod
    def _extract_test_coverage(
        bundle: EvidenceBundle,
        understanding: ChangeUnderstanding | None,
    ) -> list[TestCoverage]:
        """Extract existing test coverage information.

        Looks for test-related symbols and their coverage.
        """
        coverage: list[TestCoverage] = []
        seen: set[str] = set()

        # Extract test symbols from changed symbols
        test_symbols = [
            cs for cs in bundle.changed_symbols
            if hasattr(cs, "symbol") and (
                cs.symbol.startswith("test_") or
                cs.symbol.startswith("Test") or
                "test" in getattr(cs, "file_path", "").lower()
            )
        ]

        for ts in test_symbols:
            name = ts.symbol if hasattr(ts, "symbol") else ""
            if not name or name in seen:
                continue
            seen.add(name)

            # Infer what the test covers from its name
            covers = LlmFactsBuilder._infer_test_coverage(name)

            coverage.append(TestCoverage(
                test_name=name,
                covers=covers,
                test_file=getattr(ts, "file_path", ""),
            ))

        return coverage

    @staticmethod
    def _infer_test_coverage(test_name: str) -> list[str]:
        """Infer what a test covers from its name."""
        covers: list[str] = []
        name_lower = test_name.lower()

        # Common test name patterns
        patterns = {
            "repository": ["repository", "repo", "db_", "database", "persist"],
            "service": ["service", "business", "logic"],
            "api": ["api", "endpoint", "route", "handler", "controller", "view"],
            "validation": ["validation", "validate", "check", "assert", "guard"],
            "integration": ["integration", "e2e", "end_to_end", "flow"],
            "unit": ["unit", "test_"],
            "model": ["model", "entity", "schema"],
        }

        for domain, keywords in patterns.items():
            if any(k in name_lower for k in keywords):
                covers.append(domain)

        if not covers:
            covers.append("unit")

        return covers

    @staticmethod
    def _extract_missing_coverage(
        bundle: EvidenceBundle,
        understanding: ChangeUnderstanding | None,
    ) -> list[str]:
        """Extract symbols or paths with no test coverage.

        Looks for runtime symbols that don't have corresponding test symbols.
        """
        missing: list[str] = []
        seen: set[str] = set()

        # Get all runtime symbols
        runtime_symbols = set()
        test_symbols = set()

        for cs in bundle.changed_symbols:
            name = cs.symbol if hasattr(cs, "symbol") else ""
            if not name:
                continue
            file_path = getattr(cs, "file_path", "")
            if "test" in file_path.lower() or name.startswith("test_"):
                test_symbols.add(name)
            else:
                runtime_symbols.add(name)

        # Check which runtime symbols have corresponding tests
        for sym in sorted(runtime_symbols):
            # Check if there's a test with a matching name
            has_test = any(
                sym.lower() in t.lower() or t.lower() in sym.lower()
                for t in test_symbols
            )
            if not has_test and sym not in seen:
                seen.add(sym)
                missing.append(sym)

        return missing

    @staticmethod
    def _extract_migrations(
        bundle: EvidenceBundle,
        understanding: ChangeUnderstanding | None,
    ) -> list[MigrationFact]:
        """Extract database migration facts from evidence.

        Looks for evidence related to schema changes, column additions, etc.
        """
        migrations: list[MigrationFact] = []
        seen: set[str] = set()

        for ev in bundle.impact_evidence:
            try:
                evidence_type = ev.evidence_type
                if hasattr(evidence_type, "value"):
                    evidence_type = evidence_type.value
                evidence_type = str(evidence_type)

                if "migration" not in evidence_type.lower() and "schema" not in evidence_type.lower():
                    continue

                source = ev.source.name if hasattr(ev.source, "name") else str(ev.source)
                target = ev.target.name if hasattr(ev.target, "name") else str(ev.target)
                metadata = ev.metadata if hasattr(ev, "metadata") else {}

                key = f"{source}:{target}"
                if key in seen:
                    continue
                seen.add(key)

                migrations.append(MigrationFact(
                    table=source,
                    added_columns=[target] if target != "migration" else [],
                    nullable=metadata.get("nullable", True),
                    backfilled=metadata.get("backfilled", False),
                    detail=ev.explanation or "",
                ))
            except Exception:
                continue

        return migrations

    @staticmethod
    def _extract_review_hints(
        bundle: EvidenceBundle,
        understanding: ChangeUnderstanding | None,
    ) -> list[ReviewHint]:
        """Extract deterministic review hints from evidence.

        These are observations that may warrant reviewer attention,
        not conclusions about impact.
        """
        hints: list[ReviewHint] = []
        seen: set[str] = set()

        # Check for transaction boundary changes
        for ev in bundle.impact_evidence:
            try:
                evidence_type = ev.evidence_type
                if hasattr(evidence_type, "value"):
                    evidence_type = evidence_type.value
                evidence_type = str(evidence_type)

                hint = None
                if "transaction" in evidence_type.lower() and "boundary" in evidence_type.lower():
                    hint = "transaction boundary modified"
                elif "migration" in evidence_type.lower():
                    hint = "migration"
                elif "validation" in evidence_type.lower():
                    hint = "validation logic changed"
                elif "shared_transaction" in evidence_type.lower():
                    hint = "shared transaction boundary"
                elif "cross_domain" in evidence_type.lower():
                    hint = "cross-domain interaction"

                if hint and hint not in seen:
                    seen.add(hint)
                    hints.append(ReviewHint(hint=hint))
            except Exception:
                continue

        # Check for risk anchors
        for ra in bundle.risk_anchors:
            try:
                symbol = ra.symbol if hasattr(ra, "symbol") else ""
                anchor_type = ra.anchor_type if hasattr(ra, "anchor_type") else ""
                if hasattr(anchor_type, "value"):
                    anchor_type = anchor_type.value
                anchor_type = str(anchor_type)

                hint = f"risk anchor: {symbol} ({anchor_type})"
                if hint not in seen:
                    seen.add(hint)
                    hints.append(ReviewHint(hint=hint))
            except Exception:
                continue

        # Check for side effects
        for se in bundle.side_effects:
            try:
                symbol = se.symbol if hasattr(se, "symbol") else ""
                effect_type = se.effect_type if hasattr(se, "effect_type") else ""
                if hasattr(effect_type, "value"):
                    effect_type = effect_type.value
                effect_type = str(effect_type)

                hint = f"side effect: {symbol} ({effect_type})"
                if hint not in seen:
                    seen.add(hint)
                    hints.append(ReviewHint(hint=hint))
            except Exception:
                continue

        # Check for constraints
        for c in bundle.constraints:
            try:
                symbol = c.symbol if hasattr(c, "symbol") else ""
                constraint_type = c.constraint_type if hasattr(c, "constraint_type") else ""

                hint = f"constraint: {symbol} ({constraint_type})"
                if hint not in seen:
                    seen.add(hint)
                    hints.append(ReviewHint(hint=hint))
            except Exception:
                continue

        return hints

    @staticmethod
    def _extract_architectural_paths(
        bundle: EvidenceBundle,
        understanding: ChangeUnderstanding | None,
    ) -> list[ArchitecturalPath]:
        """Extract key architectural execution paths from evidence.

        Builds paths from impact evidence chains.
        """
        paths: list[ArchitecturalPath] = []
        seen: set[str] = set()

        # Build simple paths from evidence chains
        # Group evidence by source to find chains
        source_map: dict[str, list[str]] = {}
        for ev in bundle.impact_evidence:
            try:
                source = ev.source.name if hasattr(ev.source, "name") else str(ev.source)
                target = ev.target.name if hasattr(ev.target, "name") else str(ev.target)
                source_map.setdefault(source, []).append(target)
            except Exception:
                continue

        # Build paths from chains (source -> target1 -> target2)
        for source, targets in source_map.items():
            for target in targets:
                if target in source_map:
                    # This target is also a source, build a chain
                    for sub_target in source_map[target]:
                        path_key = f"{source} → {target} → {sub_target}"
                        if path_key not in seen:
                            seen.add(path_key)
                            paths.append(ArchitecturalPath(
                                path=[source, target, sub_target],
                                description=f"Execution path: {source} → {target} → {sub_target}",
                            ))

        # Add simple paths for remaining evidence
        for ev in bundle.impact_evidence:
            try:
                source = ev.source.name if hasattr(ev.source, "name") else str(ev.source)
                target = ev.target.name if hasattr(ev.target, "name") else str(ev.target)
                path_key = f"{source} → {target}"
                if path_key not in seen:
                    seen.add(path_key)
                    paths.append(ArchitecturalPath(
                        path=[source, target],
                        description=f"Relationship: {source} → {target}",
                    ))
            except Exception:
                continue

        return paths
"""Tests for normalized_llm_input_builder — compact packet schema."""
from __future__ import annotations

from core_engine.llm_facts import (
    LlmFacts,
    ChangedSymbolFact,
    BehaviorChange,
    Relationship,
    TestCoverage as TestCoverageFact,
    MigrationFact,
    ReviewHint,
    ArchitecturalPath,
    CompactPacket,
)
from core_engine.normalized_llm_input_builder import build_normalized_llm_input


def test_build_normalized_llm_input_produces_compact_packet():
    """Test that build_normalized_llm_input produces the new compact packet schema."""
    llm_facts = LlmFacts(
        repo="test-repo",
        pr_number=123,
        changed_symbols=[
            ChangedSymbolFact(
                symbol="redeem_discount",
                qualified_name="checkout.redeem_discount",
                kind="function",
                file_path="server/checkout/service.py",
                domain="checkout",
            ),
            ChangedSymbolFact(
                symbol="test_redeem_discount",
                kind="function",
                file_path="server/tests/checkout/test_service.py",
            ),
        ],
        behavior_changes=[
            BehaviorChange(
                type="validation",
                symbol="redeem_discount",
                change="validation logic modified",
                detail="Added email normalization check",
            ),
            BehaviorChange(
                type="persistence",
                symbol="redeem_discount",
                change="customer_email added to persistence",
                detail="Now persists customer_email",
            ),
        ],
        relationships=[
            Relationship(
                from_symbol="redeem_discount",
                to_symbol="DiscountRedemption",
                relationship_type="writes",
                detail="Persists redemption record",
            ),
            Relationship(
                from_symbol="redeem_discount",
                to_symbol="Customer",
                relationship_type="reads",
                detail="Reads customer data",
            ),
        ],
        test_coverage=[
            TestCoverageFact(
                test_name="test_redeem_discount",
                covers=["service", "validation"],
                test_file="server/tests/checkout/test_service.py",
            ),
        ],
        missing_coverage=["apply_discount"],
        migrations=[
            MigrationFact(
                table="discount_redemptions",
                added_columns=["customer_email"],
                nullable=True,
                backfilled=False,
                detail="New nullable column without backfill",
            ),
        ],
        review_hints=[
            ReviewHint(hint="validation logic changed"),
            ReviewHint(hint="migration without backfill"),
        ],
        architectural_paths=[
            ArchitecturalPath(
                path=["CheckoutService.confirm", "redeem_discount", "DiscountRedemption"],
                description="Checkout confirmation writes discount redemption",
            ),
        ],
    )

    llm_input = build_normalized_llm_input(
        llm_facts=llm_facts,
        repo="test-repo",
        pr_number=123,
    )

    # ── Top-level structure ─────────────────────────────────────────────
    # Verify compact packet sections
    assert "summary" in llm_input
    assert "symbols" in llm_input
    assert "features" in llm_input
    assert "relations" in llm_input
    assert "execution" in llm_input
    assert "coverage" in llm_input
    assert "migrations" in llm_input
    assert "hints" in llm_input
    assert "architecture" in llm_input
    assert "confidence" in llm_input

    # Old verbose fields should NOT be present
    assert "changed_symbols" not in llm_input
    assert "behavior_changes" not in llm_input
    assert "review_hints" not in llm_input
    assert "architectural_paths" not in llm_input
    assert "repo" not in llm_input
    assert "pr" not in llm_input

    # ── Summary ─────────────────────────────────────────────────────────
    assert llm_input["summary"]["files"] == 1                                   # one non-test file
    assert llm_input["summary"]["symbols"] == 4                                 # redeem_discount, DiscountRedemption, Customer, CheckoutService.confirm
    assert llm_input["summary"]["risk_patterns"] == 2                           # two review hints
    assert llm_input["summary"]["tests"] == 1                                   # one test
    assert llm_input["summary"]["migrations"] == 1                              # one migration

    # ── Symbol table ────────────────────────────────────────────────────
    symbols = llm_input["symbols"]
    assert len(symbols) == 4
    # Symbol IDs must be >= 1
    for s in symbols:
        assert s["id"] >= 1
        assert "k" in s
        assert "n" in s

    # Build name -> id map
    name_to_id = {s["n"]: s["id"] for s in symbols}
    assert "redeem_discount" in name_to_id
    assert "DiscountRedemption" in name_to_id
    assert "Customer" in name_to_id
    assert "CheckoutService.confirm" in name_to_id

    # Test symbols should be filtered out
    assert "test_redeem_discount" not in name_to_id

    # ── Feature flags ───────────────────────────────────────────────────
    features = llm_input["features"]
    assert features["validation_change"] == 1
    assert features["persistence_change"] == 1
    assert features["normalization"] == 1                                      # detected from "email normalization check"
    # Other flags should be 0
    assert features["migration"] == 0                                           # behavior change type is "persistence", not "migration"
    assert features["transaction_change"] == 0
    assert features["query_change"] == 0

    # ── Relations (graph edges) ─────────────────────────────────────────
    relations = llm_input["relations"]
    assert len(relations) == 2

    # Find the writes and reads edges
    writes_edges = [r for r in relations if r["t"] == "writes"]
    reads_edges = [r for r in relations if r["t"] == "reads"]
    assert len(writes_edges) == 1
    assert len(reads_edges) == 1

    # Verify edge structure
    writes_edge = writes_edges[0]
    assert writes_edge["from_id"] == name_to_id["redeem_discount"]
    assert writes_edge["to_id"] == name_to_id["DiscountRedemption"]
    assert writes_edge["t"] == "writes"

    reads_edge = reads_edges[0]
    assert reads_edge["from_id"] == name_to_id["redeem_discount"]
    assert reads_edge["to_id"] == name_to_id["Customer"]
    assert reads_edge["t"] == "reads"

    # ── Execution path summary ──────────────────────────────────────────
    execution = llm_input["execution"]
    assert len(execution["entrypoints"]) == 1
    assert execution["entrypoints"][0] == name_to_id["CheckoutService.confirm"]
    assert len(execution["affected_sinks"]) == 1
    assert execution["affected_sinks"][0] == name_to_id["DiscountRedemption"]
    assert execution["max_depth"] == 3

    # ── Coverage ────────────────────────────────────────────────────────
    coverage = llm_input["coverage"]
    assert coverage["unit"] == 1                                                # test_redeem_discount is a unit test
    assert coverage["integration"] == 0
    assert coverage["e2e"] == 0
    assert "service" in coverage["covered"]
    assert "validation" in coverage["covered"]
    assert "apply_discount" in coverage["missing"]

    # ── Migrations ──────────────────────────────────────────────────────
    migrations = llm_input["migrations"]
    assert len(migrations) == 1
    assert migrations[0]["table"] == "discount_redemptions"
    assert migrations[0]["cols"] == 1
    assert migrations[0]["nullable"] is True
    assert migrations[0]["backfill"] is False

    # ── Hints (enumerated signals) ──────────────────────────────────────
    hints = llm_input["hints"]
    assert len(hints) == 2
    assert "validation_logic_changed" in hints
    assert "migration_without_backfill" in hints

    # ── Architecture delta ──────────────────────────────────────────────
    architecture = llm_input["architecture"]
    assert len(architecture["new_reads"]) == 1
    assert architecture["new_reads"][0] == name_to_id["Customer"]
    assert len(architecture["new_writes"]) == 1
    assert architecture["new_writes"][0] == name_to_id["DiscountRedemption"]
    assert len(architecture["changed_calls"]) == 0                              # no calls relationships in test data

    # ── Confidence components ───────────────────────────────────────────
    confidence = llm_input["confidence"]
    assert isinstance(confidence["overall"], float)
    assert isinstance(confidence["causal"], float)
    assert isinstance(confidence["reachability"], float)
    assert isinstance(confidence["coverage"], float)
    assert confidence["overall"] == 1.0                                         # all facts present
    assert confidence["causal"] == 1.0                                          # behavior_changes and relationships present
    assert confidence["reachability"] == 1.0                                    # architectural_paths and relationships present
    assert confidence["coverage"] == 1.0                                        # test_coverage and missing_coverage present


def test_build_normalized_llm_input_empty_facts():
    """Test that build_normalized_llm_input handles empty LlmFacts."""
    llm_input = build_normalized_llm_input(
        llm_facts=LlmFacts(),
        repo="test-repo",
        pr_number=123,
    )

    assert llm_input["summary"]["files"] == 0
    assert llm_input["summary"]["symbols"] == 0
    assert llm_input["summary"]["risk_patterns"] == 0
    assert llm_input["symbols"] == []
    assert llm_input["relations"] == []
    assert llm_input["features"]["validation_change"] == 0
    assert llm_input["execution"]["entrypoints"] == []
    assert llm_input["execution"]["affected_sinks"] == []
    assert llm_input["execution"]["max_depth"] == 0
    assert llm_input["coverage"]["unit"] == 0
    assert llm_input["coverage"]["covered"] == []
    assert llm_input["coverage"]["missing"] == []
    assert llm_input["migrations"] == []
    assert llm_input["hints"] == []
    assert llm_input["architecture"]["new_reads"] == []
    assert llm_input["architecture"]["new_writes"] == []
    assert llm_input["architecture"]["changed_calls"] == []
    assert llm_input["confidence"]["overall"] < 1.0                             # empty facts reduce confidence
    assert llm_input["confidence"]["causal"] < 1.0
    assert llm_input["confidence"]["reachability"] < 1.0


def test_compact_packet_budget_enforcement():
    """Test that budget limits are enforced when data exceeds limits."""
    # Create many symbols to test budget enforcement
    many_symbols = [
        ChangedSymbolFact(
            symbol=f"symbol_{i}",
            kind="function",
            file_path=f"server/module_{i}.py",
        )
        for i in range(50)
    ]

    many_relations = [
        Relationship(
            from_symbol=f"symbol_{i}",
            to_symbol=f"symbol_{i + 1}",
            relationship_type="calls",
        )
        for i in range(45)
    ]

    llm_facts = LlmFacts(
        changed_symbols=many_symbols,
        relationships=many_relations,
    )

    llm_input = build_normalized_llm_input(llm_facts=llm_facts)

    # Symbol limit: max 40
    assert len(llm_input["symbols"]) <= 40

    # Relation limit: max 40
    assert len(llm_input["relations"]) <= 40

    # Verify we still have the structure we need
    assert "summary" in llm_input
    assert "features" in llm_input
    assert "execution" in llm_input


def test_compact_packet_no_repo_or_pr():
    """Test that compact packet does NOT include repo or pr fields."""
    llm_facts = LlmFacts(
        repo="test-repo",
        pr_number=123,
        changed_symbols=[
            ChangedSymbolFact(
                symbol="test_func",
                kind="function",
                file_path="server/module.py",
            ),
        ],
    )

    llm_input = build_normalized_llm_input(llm_facts=llm_facts)

    # The compact packet should NOT contain repo or pr at the top level
    assert "repo" not in llm_input
    assert "pr" not in llm_input

    # summary should have counts but not repo/pr
    assert "files" in llm_input["summary"]
    assert "symbols" in llm_input["summary"]
    assert "entrypoints" in llm_input["summary"]
    assert "risk_patterns" in llm_input["summary"]
    assert "tests" in llm_input["summary"]
    assert "migrations" in llm_input["summary"]
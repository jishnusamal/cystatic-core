"""
Tests for core_engine.risk_compressor
"""
from __future__ import annotations

import pytest

from core_engine.risk_compressor import (
    RISK_FAMILIES,
    RISK_WEIGHTS,
    _AREA_TO_FAMILY,
    _aggregate_by_family,
    _compute_family_score,
    _compute_family_strength,
    _get_family_for_area,
    _select_top_families,
    compress_risk_hypotheses,
)


# ═══════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture
def sample_risk_hypotheses():
    """Sample risk hypotheses covering multiple families."""
    return [
        {
            "area": "money_flow_related",
            "strength": "STRONG",
            "symbols": ["_update_checkout_tax", "_create_order_from_checkout"],
            "possible_failures": ["amount_mismatch", "settlement_discrepancy"],
        },
        {
            "area": "retry_sensitive_related",
            "strength": "MEDIUM",
            "symbols": ["handle_payment"],
            "possible_failures": ["duplicate_charge", "partial_commit"],
        },
        {
            "area": "transaction_boundary_related",
            "strength": "STRONG",
            "symbols": ["handle_payment", "finalize_order"],
            "possible_failures": ["partial_commit", "consistency_failure"],
        },
        {
            "area": "irreversible_related",
            "strength": "WEAK",
            "symbols": ["process_refund"],
            "possible_failures": ["unrecoverable_side_effect"],
        },
        {
            "area": "state_mutation_related",
            "strength": "MEDIUM",
            "symbols": ["update_order_status"],
            "possible_failures": ["invalid_state_transition"],
        },
        {
            "area": "external_dependency_related",
            "strength": "WEAK",
            "symbols": ["call_payment_gateway"],
            "possible_failures": ["unexpected_response_shape"],
        },
        {
            "area": "numeric_precision_related",
            "strength": "STRONG",
            "symbols": ["calculate_tax", "round_amount"],
            "possible_failures": ["rounding_error", "tax_calculation_error"],
        },
        {
            "area": "data_freshness_related",
            "strength": "MEDIUM",
            "symbols": ["get_latest_rates"],
            "possible_failures": ["stale_read", "reconciliation_mismatch"],
        },
    ]


@pytest.fixture
def overlapping_hypotheses():
    """Hypotheses with overlapping symbols and failures."""
    return [
        {
            "area": "money_flow_related",
            "strength": "STRONG",
            "symbols": ["_update_checkout_tax", "_create_order_from_checkout"],
            "possible_failures": ["amount_mismatch"],
        },
        {
            "area": "numeric_precision_related",
            "strength": "MEDIUM",
            "symbols": ["_update_checkout_tax", "calculate_tax"],  # overlap
            "possible_failures": ["amount_mismatch", "rounding_error"],  # overlap
        },
    ]


# ═══════════════════════════════════════════════════════════════════════════
# Step 1: Risk Families
# ═══════════════════════════════════════════════════════════════════════════

class TestRiskFamilies:
    def test_risk_families_defined(self):
        """All expected families are defined."""
        assert "financial_integrity" in RISK_FAMILIES
        assert "execution_safety" in RISK_FAMILIES
        assert "state_consistency" in RISK_FAMILIES
        assert "dependency_risk" in RISK_FAMILIES

    def test_financial_integrity_members(self):
        """financial_integrity has correct members."""
        members = RISK_FAMILIES["financial_integrity"]["members"]
        assert "money_flow_related" in members
        assert "numeric_precision_related" in members
        assert "data_freshness_related" in members

    def test_execution_safety_members(self):
        """execution_safety has correct members."""
        members = RISK_FAMILIES["execution_safety"]["members"]
        assert "retry_sensitive_related" in members
        assert "transaction_boundary_related" in members
        assert "irreversible_related" in members

    def test_area_to_family_mapping(self):
        """All family members map correctly."""
        assert _AREA_TO_FAMILY["money_flow_related"] == "financial_integrity"
        assert _AREA_TO_FAMILY["numeric_precision_related"] == "financial_integrity"
        assert _AREA_TO_FAMILY["data_freshness_related"] == "financial_integrity"
        assert _AREA_TO_FAMILY["retry_sensitive_related"] == "execution_safety"
        assert _AREA_TO_FAMILY["transaction_boundary_related"] == "execution_safety"
        assert _AREA_TO_FAMILY["irreversible_related"] == "execution_safety"
        assert _AREA_TO_FAMILY["state_mutation_related"] == "state_consistency"
        assert _AREA_TO_FAMILY["external_dependency_related"] == "dependency_risk"

    def test_unmapped_area_returns_none(self):
        """Unmapped areas return None."""
        assert _get_family_for_area("unknown_related") is None
        assert _get_family_for_area("") is None


# ═══════════════════════════════════════════════════════════════════════════
# Step 2 & 3: Aggregate Evidence and Failure Modes
# ═══════════════════════════════════════════════════════════════════════════

class TestAggregateByFamily:
    def test_aggregate_basic(self, sample_risk_hypotheses):
        """Basic aggregation produces correct families."""
        result = _aggregate_by_family(sample_risk_hypotheses)

        assert "financial_integrity" in result
        assert "execution_safety" in result
        assert "state_consistency" in result
        assert "dependency_risk" in result

    def test_symbols_deduplicated(self, overlapping_hypotheses):
        """Overlapping symbols are deduplicated within a family."""
        result = _aggregate_by_family(overlapping_hypotheses)
        family = result["financial_integrity"]

        # _update_checkout_tax appears in both, should appear only once
        assert family["symbols"].count("_update_checkout_tax") == 1
        assert "calculate_tax" in family["symbols"]
        assert "_create_order_from_checkout" in family["symbols"]

    def test_failures_deduplicated(self, overlapping_hypotheses):
        """Overlapping failures are deduplicated within a family."""
        result = _aggregate_by_family(overlapping_hypotheses)
        family = result["financial_integrity"]

        assert family["possible_failures"].count("amount_mismatch") == 1
        assert "rounding_error" in family["possible_failures"]

    def test_why_flagged_tracks_areas(self, sample_risk_hypotheses):
        """why_flagged contains all atomic areas that triggered the family."""
        result = _aggregate_by_family(sample_risk_hypotheses)
        exec_safety = result["execution_safety"]

        assert "retry_sensitive_related" in exec_safety["why_flagged"]
        assert "transaction_boundary_related" in exec_safety["why_flagged"]
        assert "irreversible_related" in exec_safety["why_flagged"]

    def test_unmapped_areas_skipped(self):
        """Areas not in RISK_FAMILIES are skipped."""
        hypotheses = [
            {"area": "unknown_related", "strength": "STRONG", "symbols": ["x"], "possible_failures": ["y"]},
        ]
        result = _aggregate_by_family(hypotheses)
        assert result == {}

    def test_empty_input(self):
        """Empty input returns empty dict."""
        result = _aggregate_by_family([])
        assert result == {}


# ═══════════════════════════════════════════════════════════════════════════
# Step 4: Calculate Family Strength
# ═══════════════════════════════════════════════════════════════════════════

class TestComputeFamilyStrength:
    def test_strong_wins(self):
        assert _compute_family_strength(["WEAK", "STRONG", "MEDIUM"]) == "STRONG"

    def test_medium_when_no_strong(self):
        assert _compute_family_strength(["WEAK", "MEDIUM"]) == "MEDIUM"

    def test_weak_when_all_weak(self):
        assert _compute_family_strength(["WEAK", "WEAK"]) == "WEAK"

    def test_empty_returns_weak(self):
        assert _compute_family_strength([]) == "WEAK"

    def test_single_strong(self):
        assert _compute_family_strength(["STRONG"]) == "STRONG"


# ═══════════════════════════════════════════════════════════════════════════
# Step 5: Calculate Family Score
# ═══════════════════════════════════════════════════════════════════════════

class TestComputeFamilyScore:
    def test_score_formula(self):
        """score = weight + symbol_count + failure_count + strength_bonus"""
        # financial_integrity (100) + 2 symbols + 2 failures + STRONG bonus (50)
        score = _compute_family_score(
            family="financial_integrity",
            strength="STRONG",
            symbol_count=2,
            failure_count=2,
        )
        assert score == 100 + 2 + 2 + 50  # 154

    def test_score_weak(self):
        # execution_safety (90) + 1 symbol + 1 failure + WEAK bonus (0)
        score = _compute_family_score(
            family="execution_safety",
            strength="WEAK",
            symbol_count=1,
            failure_count=1,
        )
        assert score == 90 + 1 + 1 + 0  # 92

    def test_unknown_family_defaults_to_zero(self):
        score = _compute_family_score(
            family="unknown_family",
            strength="WEAK",
            symbol_count=1,
            failure_count=1,
        )
        assert score == 0 + 1 + 1 + 0  # 2

    def test_medium_bonus(self):
        score = _compute_family_score(
            family="state_consistency",
            strength="MEDIUM",
            symbol_count=3,
            failure_count=2,
        )
        assert score == 50 + 3 + 2 + 25  # 80


# ═══════════════════════════════════════════════════════════════════════════
# Step 6: Keep Only Top N
# ═══════════════════════════════════════════════════════════════════════════

class TestSelectTopFamilies:
    def test_top_n_selection(self):
        items = [
            {"family": "a", "score": 10},
            {"family": "b", "score": 30},
            {"family": "c", "score": 20},
            {"family": "d", "score": 40},
        ]
        result = _select_top_families(items, top_n=2)
        assert len(result) == 2
        assert result[0]["score"] == 40
        assert result[1]["score"] == 30

    def test_sorted_descending(self):
        items = [
            {"family": "a", "score": 5},
            {"family": "b", "score": 15},
            {"family": "c", "score": 10},
        ]
        result = _select_top_families(items, top_n=3)
        scores = [r["score"] for r in result]
        assert scores == [15, 10, 5]

    def test_top_n_larger_than_input(self):
        items = [
            {"family": "a", "score": 10},
        ]
        result = _select_top_families(items, top_n=5)
        assert len(result) == 1

    def test_empty_input(self):
        result = _select_top_families([], top_n=3)
        assert result == []


# ═══════════════════════════════════════════════════════════════════════════
# Step 7 & 8: LLM-Friendly Output with Token Compression
# ═══════════════════════════════════════════════════════════════════════════

class TestCompressRiskHypotheses:
    def test_basic_compression(self, sample_risk_hypotheses):
        """Basic end-to-end compression."""
        result = compress_risk_hypotheses(sample_risk_hypotheses, top_n=3)

        assert len(result) <= 3
        for entry in result:
            assert "family" in entry
            assert "strength" in entry
            assert "score" in entry
            assert "why_flagged" in entry
            assert "symbol_count" in entry
            assert "representative_symbols" in entry
            assert "possible_failures" in entry
            # Step 8 format: no full symbols list in compressed mode
            assert "symbols" not in entry

    def test_financial_integrity_ranked_first(self, sample_risk_hypotheses):
        """financial_integrity should rank highest due to weight + multiple STRONG."""
        result = compress_risk_hypotheses(sample_risk_hypotheses, top_n=3)
        assert result[0]["family"] == "financial_integrity"

    def test_execution_safety_ranked_second(self, sample_risk_hypotheses):
        """execution_safety should rank second."""
        result = compress_risk_hypotheses(sample_risk_hypotheses, top_n=3)
        families = [r["family"] for r in result]
        assert "execution_safety" in families

    def test_symbol_count_preserved(self, sample_risk_hypotheses):
        """symbol_count reflects total deduplicated symbols."""
        result = compress_risk_hypotheses(sample_risk_hypotheses, top_n=3)
        for entry in result:
            if entry["family"] == "financial_integrity":
                # money_flow (2) + numeric_precision (2) + data_freshness (1)
                # no overlap in sample data, so total is 5
                assert entry["symbol_count"] == 5

    def test_representative_symbols_capped(self):
        """representative_symbols is capped at max_symbols (default 3)."""
        hypotheses = [
            {
                "area": "money_flow_related",
                "strength": "STRONG",
                "symbols": ["sym1", "sym2", "sym3", "sym4", "sym5"],
                "possible_failures": ["f1"],
            }
        ]
        result = compress_risk_hypotheses(hypotheses, top_n=1)
        assert len(result[0]["representative_symbols"]) <= 3

    def test_possible_failures_capped(self):
        """possible_failures is capped at max_failures (default 3)."""
        hypotheses = [
            {
                "area": "money_flow_related",
                "strength": "STRONG",
                "symbols": ["sym1"],
                "possible_failures": ["f1", "f2", "f3", "f4", "f5"],
            }
        ]
        result = compress_risk_hypotheses(hypotheses, top_n=1)
        assert len(result[0]["possible_failures"]) <= 3

    def test_why_flagged_preserved(self, sample_risk_hypotheses):
        """why_flagged contains all atomic areas for the family."""
        result = compress_risk_hypotheses(sample_risk_hypotheses, top_n=3)
        for entry in result:
            if entry["family"] == "execution_safety":
                assert "retry_sensitive_related" in entry["why_flagged"]
                assert "transaction_boundary_related" in entry["why_flagged"]
                assert "irreversible_related" in entry["why_flagged"]

    def test_full_output_mode(self, sample_risk_hypotheses):
        """When compress_for_llm=False, full symbol lists are preserved."""
        result = compress_risk_hypotheses(
            sample_risk_hypotheses,
            top_n=3,
            compress_for_llm=False,
        )
        for entry in result:
            assert "symbols" in entry
            assert "representative_symbols" not in entry
            assert "symbol_count" not in entry

    def test_empty_input(self):
        """Empty input returns empty list."""
        result = compress_risk_hypotheses([], top_n=3)
        assert result == []

    def test_no_mapped_areas(self):
        """Input with no mappable areas returns empty list."""
        hypotheses = [
            {"area": "unknown_related", "strength": "STRONG", "symbols": ["x"], "possible_failures": ["y"]},
        ]
        result = compress_risk_hypotheses(hypotheses, top_n=3)
        assert result == []

    def test_top_n_respected(self, sample_risk_hypotheses):
        """Only top_n families are returned."""
        result = compress_risk_hypotheses(sample_risk_hypotheses, top_n=2)
        assert len(result) == 2

    def test_strength_propagates_from_children(self):
        """Family strength is STRONG if any child is STRONG."""
        hypotheses = [
            {"area": "money_flow_related", "strength": "WEAK", "symbols": ["x"], "possible_failures": ["y"]},
            {"area": "numeric_precision_related", "strength": "STRONG", "symbols": ["z"], "possible_failures": ["w"]},
        ]
        result = compress_risk_hypotheses(hypotheses, top_n=1)
        assert result[0]["strength"] == "STRONG"

    def test_score_in_output(self, sample_risk_hypotheses):
        """Score is included in output."""
        result = compress_risk_hypotheses(sample_risk_hypotheses, top_n=3)
        for entry in result:
            assert "score" in entry
            assert isinstance(entry["score"], int)

    def test_no_full_symbols_in_compressed_mode(self, sample_risk_hypotheses):
        """Compressed output should NOT contain full symbols list."""
        result = compress_risk_hypotheses(sample_risk_hypotheses, top_n=3)
        for entry in result:
            assert "symbols" not in entry
            assert "representative_symbols" in entry

    def test_no_top_individual_in_output(self, sample_risk_hypotheses):
        """top_individual_hypotheses should NOT be in output (token budget)."""
        result = compress_risk_hypotheses(sample_risk_hypotheses, top_n=3)
        for entry in result:
            assert "top_individual_hypotheses" not in entry

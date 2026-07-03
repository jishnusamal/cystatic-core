"""Tests for the evidence-driven LLM packet compression pipeline."""
from __future__ import annotations

from core_engine.llm_packet_compressor import build_llm_packet, estimate_tokens
from core_engine.symbol_table import SymbolTable
from core_engine.soft_edge_compressor import compress_impact_evidence, compress_evidence_summary
from core_engine.change_influence_compressor import compress_change_influence
from core_engine.constraint_compressor import compress_constraints


def test_symbol_table():
    table = SymbolTable(max_symbols=30)
    table.build([
        {"symbol": "process_payment", "domain": "money_movement", "influence_score": 0.9, "risk_tags": ["money_flow"]},
        {"symbol": "update_inventory", "domain": "inventory", "influence_score": 0.5, "risk_tags": ["state_mutation"]},
    ])
    assert len(table) == 2
    assert table.get_id("process_payment") == "T1"
    symbols = table.to_dict()
    assert "T1" in symbols["symbols"]
    print("✓ Symbol table test passed")


def test_impact_evidence_compressor():
    impact_evidence = [
        {"source_symbol": "process_payment", "target_symbol": "charge_customer", "confidence": 0.8, "evidence_type": "canonical_flow"},
        {"source_symbol": "update_inventory", "target_symbol": "send_notification", "confidence": 0.15, "evidence_type": "naming_similarity"},
    ]
    table = SymbolTable(max_symbols=30)
    table.build([
        {"symbol": "process_payment", "domain": "money_movement", "influence_score": 0.9, "risk_tags": []},
        {"symbol": "charge_customer", "domain": "money_movement", "influence_score": 0.85, "risk_tags": []},
    ])
    compressed = compress_impact_evidence(impact_evidence, symbol_table=table, min_confidence=0.25)
    assert len(compressed) == 1
    assert compressed[0][2] == 0.8
    print("✓ Impact evidence compressor test passed")


def test_evidence_summary_compressor():
    """Test that evidence summary compression produces correct structure."""
    evidence_summary = [
        {
            "risk_area": "tax_to_invoice",
            "confidence": 0.68,
            "evidence_strength": "WEAK",
            "evidence": [
                "Tax-related symbols appear connected to invoice generation.",
                "Invoice totals appear dependent on modified tax metadata.",
            ],
            "supporting_symbols": ["_build_numeral_tax_breakdown", "create_payout_invoice", "invoice"],
        },
        {
            "risk_area": "payment_to_ledger",
            "confidence": 0.35,
            "evidence_strength": "WEAK",
            "evidence": [
                "Payment symbols appear connected to ledger flows.",
            ],
            "supporting_symbols": ["process_payment", "update_ledger"],
        },
    ]

    compressed = compress_evidence_summary(evidence_summary, max_items=10)

    assert len(compressed) == 2
    assert compressed[0]["risk_area"] == "tax_to_invoice"
    assert compressed[0]["confidence"] == 0.68
    assert compressed[0]["evidence_strength"] == "WEAK"
    assert len(compressed[0]["evidence"]) == 2
    assert len(compressed[0]["supporting_symbols"]) == 3
    print("✓ Evidence summary compressor test passed")


def test_evidence_summary_compressor_empty():
    """Test that empty evidence summary returns empty list."""
    compressed = compress_evidence_summary(None)
    assert compressed == []
    compressed = compress_evidence_summary([])
    assert compressed == []
    print("✓ Evidence summary compressor empty test passed")


def test_evidence_summary_compressor_sorts_by_confidence():
    """Test that evidence summary is sorted by confidence descending."""
    evidence_summary = [
        {
            "risk_area": "low_confidence",
            "confidence": 0.2,
            "evidence_strength": "WEAK",
            "evidence": ["Low confidence item."],
            "supporting_symbols": ["sym_a"],
        },
        {
            "risk_area": "high_confidence",
            "confidence": 0.9,
            "evidence_strength": "STRONG",
            "evidence": ["High confidence item."],
            "supporting_symbols": ["sym_b"],
        },
        {
            "risk_area": "medium_confidence",
            "confidence": 0.5,
            "evidence_strength": "MEDIUM",
            "evidence": ["Medium confidence item."],
            "supporting_symbols": ["sym_c"],
        },
    ]

    compressed = compress_evidence_summary(evidence_summary, max_items=10)

    assert len(compressed) == 3
    assert compressed[0]["risk_area"] == "high_confidence"
    assert compressed[1]["risk_area"] == "medium_confidence"
    assert compressed[2]["risk_area"] == "low_confidence"
    print("✓ Evidence summary compressor sort test passed")


def test_evidence_summary_compressor_respects_max_items():
    """Test that max_items cap is respected."""
    evidence_summary = [
        {
            "risk_area": f"area_{i}",
            "confidence": 0.5,
            "evidence_strength": "WEAK",
            "evidence": [f"Item {i}."],
            "supporting_symbols": [f"sym_{i}"],
        }
        for i in range(20)
    ]

    compressed = compress_evidence_summary(evidence_summary, max_items=5)
    assert len(compressed) == 5
    print("✓ Evidence summary compressor max_items test passed")


def test_constraint_compressor():
    constraints = {"idempotency_enabled": True, "transaction_support": False}
    compressed = compress_constraints(constraints)
    assert compressed["idempotency"] is True
    assert compressed["transactions"] is False
    print("✓ Constraint compressor test passed")


def test_build_llm_packet_with_evidence_summary():
    """Test that build_llm_packet produces risk_hypotheses instead of raw impact_evidence."""
    change_influence = [
        {"symbol": "process_payment", "domain": "money_movement", "influence_score": 0.9, "risk_tags": ["money_flow"]},
    ]
    # Pass evidence summary dicts as impact_evidence (the new pipeline)
    evidence_summary = [
        {
            "risk_area": "tax_to_invoice",
            "confidence": 0.68,
            "evidence_strength": "WEAK",
            "evidence": ["Tax-related symbols appear connected to invoice generation."],
            "supporting_symbols": ["_build_numeral_tax_breakdown", "create_payout_invoice"],
        },
    ]

    packet = build_llm_packet(
        change_influence=change_influence,
        impact_evidence=evidence_summary,
        risk_zones=["payment", "tax", "invoice"],
        changed_symbols=["process_payment"],
        repo="test/repo",
        pr_number=123,
    )

    assert "repo" in packet
    assert "change_influence" in packet
    assert "risk_hypotheses" in packet
    assert "impact_evidence" not in packet, "packet should use risk_hypotheses, not raw impact_evidence"
    assert packet["repo"] == "test/repo"
    # build_risk_hypotheses merges evidence_summary areas + tag-derived hypotheses
    assert len(packet["risk_hypotheses"]) >= 1
    areas = [h["area"] for h in packet["risk_hypotheses"]]
    assert "tax_to_invoice" in areas
    # Each hypothesis must have area, strength, symbols, possible_failures
    for hyp in packet["risk_hypotheses"]:
        assert "area" in hyp
        assert "strength" in hyp
        assert "symbols" in hyp
        assert "possible_failures" in hyp
    tokens = estimate_tokens(packet)
    assert tokens <= 8000
    print(f"✓ Build LLM packet with evidence summary test passed (tokens: {tokens})")


def test_build_llm_packet_empty_evidence():
    """Test that build_llm_packet handles empty evidence gracefully."""
    packet = build_llm_packet(
        change_influence=[],
        impact_evidence=None,
        risk_zones=[],
        changed_symbols=[],
        repo="test/repo",
        pr_number=1,
    )

    assert "risk_hypotheses" in packet
    assert packet["risk_hypotheses"] == []
    tokens = estimate_tokens(packet)
    assert tokens <= 8000
    print("✓ Build LLM packet empty evidence test passed")


def test_build_llm_packet_with_deterministic_scenarios():
    """Test that build_llm_packet produces evidence graph format when given scenarios."""
    change_influence = [
        {"symbol": "process_payment", "domain": "money_movement", "influence_score": 0.9, "risk_tags": ["money_flow"]},
    ]
    evidence_summary = [
        {
            "risk_area": "tax_to_invoice",
            "confidence": 0.68,
            "evidence_strength": "WEAK",
            "evidence": ["Tax-related symbols appear connected to invoice generation."],
            "supporting_symbols": ["_build_numeral_tax_breakdown", "create_payout_invoice"],
        },
    ]
    
    # Deterministic scenarios from inference pipeline
    deterministic_scenarios = [
        {
            "title": "Order lifecycle inconsistency",
            "narrative": "Order state may diverge from invoice state",
            "confidence": 0.84,
            "impact_type": "domain_coupling",
            "source_symbol": "update_order",
            "target_symbol": "generate_invoice",
            "description": "Order updates may not propagate to invoices",
            "reasoning": "Shared Order aggregate with transaction boundary",
            "affected_business_objects": ["Order", "Invoice", "Wallet"],
            "affected_domains": ["Billing", "Payments", "Orders"],
            "operational_impact": "Customers see mismatched order and invoice states",
            "silent_failure": True,
            "first_observable_signal": "Customer complaint about order status",
            "merge_risk_level": "HIGH",
            "ci_would_catch": False,
            "causal_chain": "update_order → OrderService → InvoiceService → generate_invoice",
            "failure_class": "state_inconsistency",
            "supported_by": ["update_order", "generate_invoice", "OrderService"],
        },
    ]
    
    business_objects = [
        {"name": "Order", "domain": "Orders"},
        {"name": "Invoice", "domain": "Billing"},
    ]
    
    constraints = [
        {"idempotency_enabled": True, "transaction_support": True},
    ]

    packet = build_llm_packet(
        change_influence=change_influence,
        impact_evidence=evidence_summary,
        risk_zones=["payment", "tax", "invoice"],
        changed_symbols=["process_payment"],
        repo="test/repo",
        pr_number=123,
        deterministic_scenarios=deterministic_scenarios,
        business_objects=business_objects,
        domains=["payment", "billing", "order"],
        constraints=constraints,
    )

    # Legacy format still present
    assert "repo" in packet
    assert "change_influence" in packet
    assert "risk_hypotheses" in packet
    
    # Note: Evidence graph scenarios have been moved to the normalization layer
    # The deprecated build_llm_packet no longer includes scenarios or summary
    # Use core_engine.llm_input_builder.build_llm_input() for reviewer-ready facts
    
    tokens = estimate_tokens(packet)
    assert tokens <= 8000
    print(f"✓ Build LLM packet with deterministic scenarios test passed (tokens: {tokens})")


def test_schema_allows_review_required_without_scenarios():
    """Test that REVIEW_REQUIRED verdict is valid with executive_summary but no scenarios.
    
    This is the hybrid architecture: LLM acts as reviewer, not scenario generator.
    It provides executive_summary, primary_concern, etc. without generating scenarios.
    """
    from schemas.failure_simulation import FailureSimulationOutput
    
    # LLM reviewer output: REVIEW_REQUIRED with executive_summary but no scenarios
    output = FailureSimulationOutput(
        verdict="REVIEW_REQUIRED",
        executive_summary="Tax-related symbols span checkout, order creation, and invoice generation. Risk of tax drift in production.",
        reviewer_questions=["Can you add an end-to-end test that verifies tax consistency?"],
    )
    
    assert output.verdict == "REVIEW_REQUIRED"
    assert len(output.executive_summary) >= 30
    print("✓ Schema allows REVIEW_REQUIRED without scenarios (hybrid architecture)")


def test_schema_requires_substantive_output_for_block():
    """Test that BLOCK requires either executive_summary or primary_concern."""
    from schemas.failure_simulation import FailureSimulationOutput
    from pydantic import ValidationError
    
    # Should fail: BLOCK with no substantive output
    try:
        output = FailureSimulationOutput(
            verdict="BLOCK",
            executive_summary="",  # Too short
        )
        assert False, "Should have raised ValidationError"
    except ValidationError as e:
        assert "requires a primary_concern" in str(e)
        print("✓ Schema correctly rejects BLOCK without substantive output")
    
    # Should succeed: BLOCK with primary_concern
    output = FailureSimulationOutput(
        verdict="BLOCK",
        executive_summary="Authentication bypass vulnerability in login flow.",
        primary_concern={
            "title": "Authentication bypass",
            "why_blocking": "The change removes authentication checks in the login flow, allowing unauthorized access to user data.",
            "execution_path": "login_handler → authenticate → authorize",
            "customer_or_business_impact": "Unauthorized access to all user accounts",
            "why_existing_tests_miss_it": "Existing tests mock authentication and do not test the actual bypass path",
            "confidence_rationale": "Deterministic analysis confirms the authentication check removal is reachable from the public login endpoint",
            "required_validation": "End-to-end test that verifies authentication is enforced on the login path",
        },
        reviewer_questions=["How do you plan to address the authentication bypass?"],
    )
    assert output.verdict == "BLOCK"
    print("✓ Schema allows BLOCK with primary_concern")


if __name__ == "__main__":
    test_symbol_table()
    test_impact_evidence_compressor()
    test_evidence_summary_compressor()
    test_evidence_summary_compressor_empty()
    test_evidence_summary_compressor_sorts_by_confidence()
    test_evidence_summary_compressor_respects_max_items()
    test_constraint_compressor()
    test_build_llm_packet_with_evidence_summary()
    test_build_llm_packet_empty_evidence()
    test_build_llm_packet_with_deterministic_scenarios()
    test_schema_allows_review_required_without_scenarios()
    test_schema_requires_substantive_output_for_block()
    print("\n✅ All tests passed!")

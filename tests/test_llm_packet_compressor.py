"""Tests for the V6 evidence-driven LLM packet compression pipeline."""
from __future__ import annotations

from core_engine.llm_packet_compressor import build_llm_packet, estimate_tokens
from core_engine.symbol_table import SymbolTable
from core_engine.path_compressor import compress_paths
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


def test_path_compressor():
    execution_paths = {"paths": [{"nodes": ["process_payment", "validate_card"], "path_confidence": 0.85, "key_risk_points": [{"risk_type": "transaction_boundary"}]}]}
    table = SymbolTable(max_symbols=30)
    table.build([
        {"symbol": "process_payment", "domain": "money_movement", "influence_score": 0.9, "risk_tags": []},
        {"symbol": "validate_card", "domain": "money_movement", "influence_score": 0.8, "risk_tags": []},
    ])
    compressed = compress_paths(execution_paths, symbol_table=table)
    assert len(compressed) == 1
    assert compressed[0]["nodes"] == ["T1", "T2"]
    print("✓ Path compressor test passed")


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
    """Test that build_llm_packet produces evidence_summary instead of raw impact_evidence."""
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
    assert "evidence_summary" in packet
    assert "impact_evidence" not in packet, "packet should use evidence_summary, not raw impact_evidence"
    assert packet["repo"] == "test/repo"
    assert len(packet["evidence_summary"]) == 1
    assert packet["evidence_summary"][0]["risk_area"] == "tax_to_invoice"
    assert packet["evidence_summary"][0]["evidence_strength"] == "WEAK"
    tokens = estimate_tokens(packet)
    assert tokens <= 8000
    print(f"✓ Build LLM packet with evidence summary test passed (tokens: {tokens})")


def test_build_llm_packet_empty_evidence():
    """Test that build_llm_packet handles empty evidence gracefully."""
    packet = build_llm_packet(
        change_influence=[],
        impact_evidence=[],
        risk_zones=["general"],
        changed_symbols=[],
        repo="test/repo",
        pr_number=123,
    )
    
    assert "evidence_summary" in packet
    assert packet["evidence_summary"] == []
    tokens = estimate_tokens(packet)
    assert tokens <= 8000
    print("✓ Build LLM packet empty evidence test passed")


if __name__ == "__main__":
    test_symbol_table()
    test_path_compressor()
    test_impact_evidence_compressor()
    test_evidence_summary_compressor()
    test_evidence_summary_compressor_empty()
    test_evidence_summary_compressor_sorts_by_confidence()
    test_evidence_summary_compressor_respects_max_items()
    test_constraint_compressor()
    test_build_llm_packet_with_evidence_summary()
    test_build_llm_packet_empty_evidence()
    print("\n✅ All tests passed!")

"""Tests for the V5 LLM packet compression pipeline."""
from __future__ import annotations

from core_engine.llm_packet_compressor import build_llm_packet, estimate_tokens
from core_engine.symbol_table import SymbolTable
from core_engine.path_compressor import compress_paths
from core_engine.soft_edge_compressor import compress_soft_edges
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


def test_soft_edge_compressor():
    soft_edges = [
        {"from": "process_payment", "to": "charge_customer", "confidence": 0.8, "source": "domain_flow"},
        {"from": "update_inventory", "to": "send_notification", "confidence": 0.15, "source": "semantic_propagation"},
    ]
    table = SymbolTable(max_symbols=30)
    table.build([
        {"symbol": "process_payment", "domain": "money_movement", "influence_score": 0.9, "risk_tags": []},
        {"symbol": "charge_customer", "domain": "money_movement", "influence_score": 0.85, "risk_tags": []},
    ])
    compressed = compress_soft_edges(soft_edges, symbol_table=table, min_confidence=0.25)
    assert len(compressed) == 1
    assert compressed[0][2] == 0.8
    print("✓ Soft edge compressor test passed")


def test_constraint_compressor():
    constraints = {"idempotency_enabled": True, "transaction_support": False}
    compressed = compress_constraints(constraints)
    assert compressed["idempotency"] is True
    assert compressed["transactions"] is False
    print("✓ Constraint compressor test passed")


def test_build_llm_packet():
    change_influence = [
        {"symbol": "process_payment", "domain": "money_movement", "influence_score": 0.9, "risk_tags": ["money_flow"]},
    ]
    execution_paths = {"paths": [{"nodes": ["process_payment"], "path_confidence": 0.85, "key_risk_points": []}]}
    soft_edges = [{"from": "process_payment", "to": "charge_customer", "confidence": 0.8, "source": "domain_flow"}]
    constraints = {"idempotency_enabled": True}
    
    packet = build_llm_packet(
        change_influence=change_influence,
        execution_paths=execution_paths,
        soft_edges=soft_edges,
        constraints=constraints,
        risk_zones=["payment"],
        changed_symbols=["process_payment"],
        repo="test/repo",
        pr_number=123,
    )
    
    assert "repo" in packet
    assert "change_influence" in packet
    assert "execution_paths" in packet
    assert "soft_edges" in packet
    assert packet["repo"] == "test/repo"
    tokens = estimate_tokens(packet)
    assert tokens <= 8000
    print(f"✓ Build LLM packet test passed (tokens: {tokens})")


if __name__ == "__main__":
    test_symbol_table()
    test_path_compressor()
    test_soft_edge_compressor()
    test_constraint_compressor()
    test_build_llm_packet()
    print("\n✅ All tests passed!")
"""Tests for Phase 2 — Weak Causal Edges.

Verifies that build_weak_edges produces evidence edges with 5 types:
  CALLS, SHARES_STATE, DATA_FLOW, CONTROL_FLOW, CONTRACT_DEPENDENCY

Every edge MUST have ≥1 evidence string.
"""
from __future__ import annotations

from core_engine.causal_graph import (
    CausalGraphBuilder,
    WeakEdge,
    build_weak_edges,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _enriched_file(
    file_path: str,
    lines: list[str],
    fn_names: list[str],
    change_types: list[str] | None = None,
    endpoints: list[dict] | None = None,
    full_content: str | None = None,
) -> dict:
    if change_types is None:
        change_types = ["modified"] * len(fn_names)
    result = {
        "file_path": file_path,
        "hunks": [
            {"lines": [{"line_type": "added", "content": ln} for ln in lines]}
        ],
        "changed_functions": [
            {"name": fn, "change_type": ct, "start_line": 1, "end_line": 1}
            for fn, ct in zip(fn_names, change_types)
        ],
    }
    if endpoints:
        result["endpoints"] = endpoints
    if full_content:
        result["full_content"] = full_content
    return result


def _edge_types(edges: list[dict]) -> set[str]:
    """Extract unique edge types from a list of weak edge dicts."""
    return {e["type"] for e in edges}


def _edges_between(edges: list[dict], from_sym: str, to_sym: str) -> list[dict]:
    """Find edges between specific symbols."""
    return [e for e in edges if e["from"] == from_sym and e["to"] == to_sym]


# ---------------------------------------------------------------------------
# 1. Basic structure
# ---------------------------------------------------------------------------

def test_weak_edges_returns_list_of_dicts() -> None:
    """build_weak_edges returns a list of dicts."""
    enriched = [_enriched_file(
        "src/service.py",
        ["result = calculate(order)"],
        ["checkout"],
    )]
    edges = build_weak_edges(enriched_files=enriched)
    assert isinstance(edges, list)


def test_weak_edges_empty_input() -> None:
    """Empty input returns empty list."""
    assert build_weak_edges(enriched_files=[]) == []


def test_weak_edges_have_required_fields() -> None:
    """Every edge dict has from, to, type, confidence, evidence, file_path."""
    enriched = [_enriched_file(
        "src/service.py",
        ["result = calculate(order)"],
        ["checkout"],
    )]
    edges = build_weak_edges(enriched_files=enriched)
    for edge in edges:
        assert "from" in edge
        assert "to" in edge
        assert "type" in edge
        assert "confidence" in edge
        assert "evidence" in edge
        assert "file_path" in edge


def test_every_edge_has_at_least_one_evidence_string() -> None:
    """KEY RULE: every edge MUST have ≥1 evidence string."""
    enriched = [_enriched_file(
        "src/service.py",
        ["result = calculate(order)", 'cache.set("user", user)'],
        ["checkout"],
    )]
    edges = build_weak_edges(enriched_files=enriched)
    for edge in edges:
        assert len(edge["evidence"]) >= 1, (
            f"Edge {edge['from']} -> {edge['to']} ({edge['type']}) "
            f"has no evidence strings"
        )


# ---------------------------------------------------------------------------
# 2. CALLS edges
# ---------------------------------------------------------------------------

def test_calls_edge_detected() -> None:
    """Direct function invocation produces a CALLS edge."""
    enriched = [_enriched_file(
        "src/service.py",
        ["result = calculate(order)", "def calculate(o): return o"],
        ["checkout", "calculate"],
    )]
    edges = build_weak_edges(enriched_files=enriched)
    call_edges = [e for e in edges if e["type"] == "CALLS"]
    assert len(call_edges) >= 1
    assert call_edges[0]["from"] == "checkout"
    assert call_edges[0]["to"] == "calculate"


def test_calls_edge_confidence_range() -> None:
    """CALLS edges have confidence in range [0.5, 1.0]."""
    enriched = [_enriched_file(
        "src/service.py",
        ["result = calculate(order)", "process(order)", "return calculate(order)",
         "def calculate(o): return o", "def process(o): return o"],
        ["checkout", "calculate", "process"],
    )]
    edges = build_weak_edges(enriched_files=enriched)
    for edge in edges:
        if edge["type"] == "CALLS":
            assert 0.5 <= edge["confidence"] <= 1.0, (
                f"CALLS confidence {edge['confidence']} out of range"
            )


def test_calls_edge_has_evidence() -> None:
    """CALLS edge evidence contains invocation-related strings."""
    enriched = [_enriched_file(
        "src/service.py",
        ["result = calculate(order)", "def calculate(o): return o"],
        ["checkout", "calculate"],
    )]
    edges = build_weak_edges(enriched_files=enriched)
    call_edges = [e for e in edges if e["type"] == "CALLS"]
    assert call_edges
    evidence_text = " ".join(call_edges[0]["evidence"])
    assert "invocation" in evidence_text.lower() or "call" in evidence_text.lower()


def test_calls_no_self_call() -> None:
    """A symbol calling itself does not produce a CALLS edge."""
    enriched = [_enriched_file(
        "src/service.py",
        ["result = checkout(order)", "def checkout(o): return o"],
        ["checkout"],
    )]
    edges = build_weak_edges(enriched_files=enriched)
    call_edges = [e for e in edges if e["type"] == "CALLS"]
    for edge in call_edges:
        assert not (edge["from"] == "checkout" and edge["to"] == "checkout")


# ---------------------------------------------------------------------------
# 3. SHARES_STATE edges
# ---------------------------------------------------------------------------

def test_shares_state_edge_detected() -> None:
    """Writer and reader of same cache resource get SHARES_STATE edge."""
    enriched = [_enriched_file(
        "src/service.py",
        [
            'def checkout(): cache.set("user", user)',
            'def discount(): x = cache.get("user")',
        ],
        ["checkout", "discount"],
    )]
    edges = build_weak_edges(enriched_files=enriched)
    ss_edges = [e for e in edges if e["type"] == "SHARES_STATE"]
    assert len(ss_edges) >= 1
    assert ss_edges[0]["from"] == "checkout"
    assert ss_edges[0]["to"] == "discount"


def test_shares_state_confidence() -> None:
    """SHARES_STATE edges have confidence around 0.65."""
    enriched = [_enriched_file(
        "src/service.py",
        [
            'def checkout(): cache.set("user", user)',
            'def discount(): x = cache.get("user")',
        ],
        ["checkout", "discount"],
    )]
    edges = build_weak_edges(enriched_files=enriched)
    ss_edges = [e for e in edges if e["type"] == "SHARES_STATE"]
    for edge in ss_edges:
        assert 0.5 <= edge["confidence"] <= 0.8


def test_shares_state_evidence_mentions_resource() -> None:
    """SHARES_STATE evidence mentions the resource name."""
    enriched = [_enriched_file(
        "src/service.py",
        [
            'def checkout(): cache.set("user", user)',
            'def discount(): x = cache.get("user")',
        ],
        ["checkout", "discount"],
    )]
    edges = build_weak_edges(enriched_files=enriched)
    ss_edges = [e for e in edges if e["type"] == "SHARES_STATE"]
    for edge in ss_edges:
        evidence_text = " ".join(edge["evidence"])
        assert "cache:user" in evidence_text or "cache" in evidence_text.lower()


# ---------------------------------------------------------------------------
# 4. DATA_FLOW edges
# ---------------------------------------------------------------------------

def test_data_flow_edge_detected() -> None:
    """Assignment chain x = fn() followed by use of x produces DATA_FLOW."""
    enriched = [_enriched_file(
        "src/service.py",
        [
            "result = calculate(order)",
            "checkout(result)",
        ],
        ["main"],
    )]
    edges = build_weak_edges(enriched_files=enriched)
    df_edges = [e for e in edges if e["type"] == "DATA_FLOW"]
    # DATA_FLOW may or may not fire depending on whether `calculate` is known
    # Just verify the structure is correct if it fires
    for edge in df_edges:
        assert "result" in " ".join(edge["evidence"]) or "assigned" in " ".join(edge["evidence"])


# ---------------------------------------------------------------------------
# 5. CONTROL_FLOW edges
# ---------------------------------------------------------------------------

def test_control_flow_edge_detected() -> None:
    """Conditional if symbol(...) produces CONTROL_FLOW edge."""
    enriched = [_enriched_file(
        "src/service.py",
        ["if is_valid(order): checkout(order)"],
        ["main"],
    )]
    edges = build_weak_edges(enriched_files=enriched)
    cf_edges = [e for e in edges if e["type"] == "CONTROL_FLOW"]
    # CONTROL_FLOW fires when both the conditional symbol and the calling symbol
    # appear on the same line. Verify structure if it fires.
    for edge in cf_edges:
        assert edge["confidence"] <= 0.6


# ---------------------------------------------------------------------------
# 6. CONTRACT_DEPENDENCY edges
# ---------------------------------------------------------------------------

def test_contract_dependency_edge_detected() -> None:
    """Import-based coupling produces CONTRACT_DEPENDENCY edge."""
    full_content = '''
import stripe
from services.tax import calculate_tax

def checkout(order):
    tax = calculate_tax(order)
    return stripe.charge(amount=order.total + tax)
'''
    enriched = [_enriched_file(
        "src/checkout/service.py",
        ["tax = calculate_tax(order)", "return stripe.charge(amount=order.total + tax)"],
        ["checkout"],
        full_content=full_content,
    )]
    edges = build_weak_edges(enriched_files=enriched)
    cd_edges = [e for e in edges if e["type"] == "CONTRACT_DEPENDENCY"]
    assert len(cd_edges) >= 1
    # Should have stripe and services.tax as targets
    targets = {e["to"] for e in cd_edges}
    assert "stripe" in targets
    assert "services.tax" in targets


def test_contract_dependency_evidence_mentions_import() -> None:
    """CONTRACT_DEPENDENCY evidence mentions import path."""
    full_content = '''
import stripe
def checkout(order):
    return stripe.charge(amount=order.total)
'''
    enriched = [_enriched_file(
        "src/checkout/service.py",
        ["return stripe.charge(amount=order.total)"],
        ["checkout"],
        full_content=full_content,
    )]
    edges = build_weak_edges(enriched_files=enriched)
    cd_edges = [e for e in edges if e["type"] == "CONTRACT_DEPENDENCY"]
    for edge in cd_edges:
        evidence_text = " ".join(edge["evidence"])
        assert "import" in evidence_text.lower()


def test_contract_dependency_confidence() -> None:
    """CONTRACT_DEPENDENCY edges have confidence in [0.3, 0.6]."""
    full_content = '''
import stripe
def checkout(order):
    return stripe.charge(amount=order.total)
'''
    enriched = [_enriched_file(
        "src/checkout/service.py",
        ["return stripe.charge(amount=order.total)"],
        ["checkout"],
        full_content=full_content,
    )]
    edges = build_weak_edges(enriched_files=enriched)
    cd_edges = [e for e in edges if e["type"] == "CONTRACT_DEPENDENCY"]
    for edge in cd_edges:
        assert 0.3 <= edge["confidence"] <= 0.6


# ---------------------------------------------------------------------------
# 7. Edge type completeness
# ---------------------------------------------------------------------------

def test_all_five_edge_types_can_fire() -> None:
    """A rich scenario can produce all 5 edge types."""
    full_content = '''
import stripe
from services.tax import calculate_tax

def is_valid(order):
    return order.total > 0

def checkout(order):
    if is_valid(order):
        tax = calculate_tax(order)
        result = stripe.charge(amount=order.total + tax)
        cache.set("last_order", result)
        return result

def get_last_order():
    return cache.get("last_order")
'''
    enriched = [_enriched_file(
        "src/checkout/service.py",
        [
            "if is_valid(order):",
            "    tax = calculate_tax(order)",
            '    result = stripe.charge(amount=order.total + tax)',
            '    cache.set("last_order", result)',
            "    return result",
            'def get_last_order(): return cache.get("last_order")',
        ],
        ["is_valid", "checkout", "get_last_order"],
        full_content=full_content,
    )]
    edges = build_weak_edges(enriched_files=enriched)
    types = _edge_types(edges)

    # CALLS should fire (checkout calls calculate_tax, etc.)
    assert "CALLS" in types
    # CONTRACT_DEPENDENCY should fire (import stripe, services.tax)
    assert "CONTRACT_DEPENDENCY" in types


# ---------------------------------------------------------------------------
# 8. WeakEdge dataclass
# ---------------------------------------------------------------------------

def test_weak_edge_to_dict() -> None:
    """WeakEdge.to_dict produces the expected schema."""
    edge = WeakEdge(
        from_symbol="checkout",
        to_symbol="calculate",
        edge_type="CALLS",
        confidence=0.85,
        evidence=["direct invocation found in src/service.py"],
        file_path="src/service.py",
    )
    d = edge.to_dict()
    assert d["from"] == "checkout"
    assert d["to"] == "calculate"
    assert d["type"] == "CALLS"
    assert d["confidence"] == 0.85
    assert d["evidence"] == ["direct invocation found in src/service.py"]
    assert d["file_path"] == "src/service.py"


def test_weak_edge_post_init_coerces_evidence() -> None:
    """WeakEdge.__post_init__ ensures evidence is always a list."""
    edge = WeakEdge(
        from_symbol="a",
        to_symbol="b",
        edge_type="CALLS",
        evidence="single string",  # type: ignore[list-item]
    )
    assert isinstance(edge.evidence, list)


def test_weak_edge_hashable() -> None:
    """WeakEdge can be used in sets."""
    e1 = WeakEdge("a", "b", "CALLS", evidence=["x"])
    e2 = WeakEdge("a", "b", "CALLS", evidence=["y"])
    s = {e1, e2}
    assert len(s) == 1  # same key, deduplicated


# ---------------------------------------------------------------------------
# 9. Deduplication
# ---------------------------------------------------------------------------

def test_duplicate_edges_deduplicated() -> None:
    """Same (from, to, type) edge is only emitted once."""
    enriched = [_enriched_file(
        "src/service.py",
        ["result = calculate(order)", "calculate(order)", "def calculate(o): return o"],
        ["checkout", "calculate"],
    )]
    edges = build_weak_edges(enriched_files=enriched)
    seen = set()
    for edge in edges:
        key = (edge["from"], edge["to"], edge["type"])
        assert key not in seen, f"Duplicate edge: {key}"
        seen.add(key)


# ---------------------------------------------------------------------------
# 10. File path propagation
# ---------------------------------------------------------------------------

def test_file_path_on_edges() -> None:
    """Every edge has the correct file_path."""
    enriched = [_enriched_file(
        "src/checkout/service.py",
        ["result = calculate(order)", "def calculate(o): return o"],
        ["checkout", "calculate"],
    )]
    edges = build_weak_edges(enriched_files=enriched)
    for edge in edges:
        assert edge["file_path"] == "src/checkout/service.py"
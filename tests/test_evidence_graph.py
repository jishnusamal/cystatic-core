"""Tests for Phase 1 — Evidence Graph.

Verifies that each changed symbol is enriched with behavioral signals:
  - is_entrypoint: detected from HTTP route decorators
  - is_io: detected from network/file I/O patterns
  - writes_state: shared state mutation detection
  - reads_state: shared state read detection (resource names)
  - calls: function call targets extracted from changed lines
  - called_by: reverse callers from causal graph edges
  - imports: module imports from file AST
"""
from __future__ import annotations

from core_engine.causal_graph import (
    CausalGraphBuilder,
    EvidenceNode,
    RepositorySymbolIndex,
    SymbolSignals,
    build_evidence_graph,
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
    """Build an enriched_file dict for testing."""
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


# ---------------------------------------------------------------------------
# 1. Basic evidence graph structure
# ---------------------------------------------------------------------------

def test_evidence_graph_returns_list_of_dicts() -> None:
    """build_evidence_graph returns a list of dicts matching EvidenceNode.to_dict."""
    enriched = [_enriched_file(
        "src/checkout.py",
        ["result = calculate_tax(order)"],
        ["checkout"],
    )]
    graph = build_evidence_graph(enriched_files=enriched)
    assert isinstance(graph, list)
    assert len(graph) == 1
    node = graph[0]
    assert node["symbol"] == "checkout"
    assert node["file"] == "src/checkout.py"
    assert node["change_type"] == "modified"
    assert "signals" in node
    assert isinstance(node["signals"], dict)


def test_evidence_graph_empty_input() -> None:
    """Empty input returns empty list."""
    assert build_evidence_graph(enriched_files=[]) == []


def test_evidence_graph_multiple_symbols() -> None:
    """Multiple changed functions produce multiple evidence nodes."""
    enriched = [_enriched_file(
        "src/service.py",
        ["a()", "b()"],
        ["func_a", "func_b"],
    )]
    graph = build_evidence_graph(enriched_files=enriched)
    symbols = {n["symbol"] for n in graph}
    assert "func_a" in symbols
    assert "func_b" in symbols


def test_evidence_graph_multiple_files() -> None:
    """Changed functions across multiple files are all included."""
    enriched = [
        _enriched_file("src/a.py", ["x()"], ["func_a"]),
        _enriched_file("src/b.py", ["y()"], ["func_b"]),
    ]
    graph = build_evidence_graph(enriched_files=enriched)
    files = {n["file"] for n in graph}
    assert "src/a.py" in files
    assert "src/b.py" in files


# ---------------------------------------------------------------------------
# 2. is_entrypoint signal
# ---------------------------------------------------------------------------

def test_entrypoint_from_enriched_endpoints() -> None:
    """Symbol with matching endpoint in enriched file is marked as entrypoint."""
    enriched = [_enriched_file(
        "src/api.py",
        ["return get_order(order_id)"],
        ["get_order"],
        endpoints=[{"function": "get_order", "route": "/orders/{id}", "method": "GET"}],
    )]
    graph = build_evidence_graph(enriched_files=enriched)
    node = next(n for n in graph if n["symbol"] == "get_order")
    assert node["signals"]["is_entrypoint"] is True


def test_entrypoint_from_full_content_ast() -> None:
    """Symbol with @router.get decorator in full_content is detected as entrypoint."""
    full_content = '''
from fastapi import APIRouter
router = APIRouter()

@router.get("/orders/{order_id}")
async def get_order(order_id: int):
    return {"id": order_id}
'''
    enriched = [_enriched_file(
        "src/api.py",
        ['return {"id": order_id}'],
        ["get_order"],
        full_content=full_content,
    )]
    graph = build_evidence_graph(enriched_files=enriched)
    node = next(n for n in graph if n["symbol"] == "get_order")
    assert node["signals"]["is_entrypoint"] is True


def test_entrypoint_from_repo_index() -> None:
    """Symbol with endpoint in repo_index is detected as entrypoint."""
    repo_index = RepositorySymbolIndex(
        known_symbols={"get_order"},
        all_endpoints=[{"function": "get_order", "route": "/orders", "method": "GET"}],
    )
    enriched = [_enriched_file(
        "src/api.py",
        ['return get_order(order_id)'],
        ["get_order"],
    )]
    graph = build_evidence_graph(enriched_files=enriched, repo_index=repo_index)
    node = next(n for n in graph if n["symbol"] == "get_order")
    assert node["signals"]["is_entrypoint"] is True


def test_non_entrypoint_symbol() -> None:
    """Symbol without any route decorator is not an entrypoint."""
    enriched = [_enriched_file(
        "src/service.py",
        ["x = calculate(a, b)"],
        ["helper"],
    )]
    graph = build_evidence_graph(enriched_files=enriched)
    node = next(n for n in graph if n["symbol"] == "helper")
    assert node["signals"]["is_entrypoint"] is False


# ---------------------------------------------------------------------------
# 3. is_io signal
# ---------------------------------------------------------------------------

def test_io_detected_requests() -> None:
    """Symbol with requests.get() call is detected as I/O."""
    enriched = [_enriched_file(
        "src/client.py",
        ['resp = requests.get("https://api.example.com")'],
        ["fetch_data"],
    )]
    graph = build_evidence_graph(enriched_files=enriched)
    node = next(n for n in graph if n["symbol"] == "fetch_data")
    assert node["signals"]["is_io"] is True


def test_io_detected_httpx() -> None:
    """Symbol with httpx call is detected as I/O."""
    enriched = [_enriched_file(
        "src/client.py",
        ["resp = httpx.get(url)"],
        ["fetch_data"],
    )]
    graph = build_evidence_graph(enriched_files=enriched)
    node = next(n for n in graph if n["symbol"] == "fetch_data")
    assert node["signals"]["is_io"] is True


def test_io_detected_open() -> None:
    """Symbol with open() call is detected as I/O."""
    enriched = [_enriched_file(
        "src/file_ops.py",
        ['data = open("file.txt").read()'],
        ["read_file"],
    )]
    graph = build_evidence_graph(enriched_files=enriched)
    node = next(n for n in graph if n["symbol"] == "read_file")
    assert node["signals"]["is_io"] is True


def test_no_io_signal() -> None:
    """Symbol without I/O patterns has is_io=False."""
    enriched = [_enriched_file(
        "src/math.py",
        ["result = x + y"],
        ["add"],
    )]
    graph = build_evidence_graph(enriched_files=enriched)
    node = next(n for n in graph if n["symbol"] == "add")
    assert node["signals"]["is_io"] is False


# ---------------------------------------------------------------------------
# 4. writes_state / reads_state signals
# ---------------------------------------------------------------------------

def test_writes_state_cache_set() -> None:
    """cache.set() is detected as state write."""
    enriched = [_enriched_file(
        "src/cache.py",
        ['cache.set("user", user_obj)'],
        ["update_user"],
    )]
    graph = build_evidence_graph(enriched_files=enriched)
    node = next(n for n in graph if n["symbol"] == "update_user")
    assert node["signals"]["writes_state"] is True


def test_writes_state_session() -> None:
    """session["token"] = v is detected as state write."""
    enriched = [_enriched_file(
        "src/auth.py",
        ['session["token"] = new_token'],
        ["login"],
    )]
    graph = build_evidence_graph(enriched_files=enriched)
    node = next(n for n in graph if n["symbol"] == "login")
    assert node["signals"]["writes_state"] is True


def test_reads_state_cache_get() -> None:
    """cache.get("key") is detected as state read with resource name."""
    enriched = [_enriched_file(
        "src/service.py",
        ['user = cache.get("user")'],
        ["get_user"],
    )]
    graph = build_evidence_graph(enriched_files=enriched)
    node = next(n for n in graph if n["symbol"] == "get_user")
    assert node["signals"]["reads_state"] == ["cache:user"]


def test_reads_state_session_subscript() -> None:
    """session["token"] read is detected as state read."""
    enriched = [_enriched_file(
        "src/auth.py",
        ['token = session["token"]'],
        ["check_auth"],
    )]
    graph = build_evidence_graph(enriched_files=enriched)
    node = next(n for n in graph if n["symbol"] == "check_auth")
    assert "session:token" in node["signals"]["reads_state"]


def test_no_state_access() -> None:
    """Symbol without shared state access has no state signals."""
    enriched = [_enriched_file(
        "src/math.py",
        ["result = x + y"],
        ["add"],
    )]
    graph = build_evidence_graph(enriched_files=enriched)
    node = next(n for n in graph if n["symbol"] == "add")
    assert node["signals"]["writes_state"] is False
    assert node["signals"]["reads_state"] == []


# ---------------------------------------------------------------------------
# 5. calls signal
# ---------------------------------------------------------------------------

def test_calls_detected() -> None:
    """Function calls in changed lines are extracted as 'calls' signal."""
    enriched = [_enriched_file(
        "src/checkout.py",
        ["result = calculate_tax(order)", "handle_payment(order)"],
        ["checkout"],
    )]
    graph = build_evidence_graph(enriched_files=enriched)
    node = next(n for n in graph if n["symbol"] == "checkout")
    assert "calculate_tax" in node["signals"]["calls"]
    assert "handle_payment" in node["signals"]["calls"]


def test_calls_filters_builtins() -> None:
    """Builtins and control flow keywords are filtered from calls."""
    enriched = [_enriched_file(
        "src/service.py",
        ["if len(x): return str(y)"],
        ["process"],
    )]
    graph = build_evidence_graph(enriched_files=enriched)
    node = next(n for n in graph if n["symbol"] == "process")
    assert "len" not in node["signals"]["calls"]
    assert "str" not in node["signals"]["calls"]
    assert "if" not in node["signals"]["calls"]


def test_calls_deduplicated() -> None:
    """Multiple calls to the same function are deduplicated."""
    enriched = [_enriched_file(
        "src/service.py",
        ["calculate(x)", "calculate(y)"],
        ["process"],
    )]
    graph = build_evidence_graph(enriched_files=enriched)
    node = next(n for n in graph if n["symbol"] == "process")
    assert node["signals"]["calls"].count("calculate") == 1


# ---------------------------------------------------------------------------
# 6. called_by signal (backfill from cross-function calls)
# ---------------------------------------------------------------------------

def test_called_by_from_same_file() -> None:
    """When A calls B, B's called_by should include A."""
    enriched = [_enriched_file(
        "src/service.py",
        ["result = helper(x)"],
        ["main"],
    )]
    # Also add helper as a changed function so it's in the evidence graph
    enriched[0]["changed_functions"].append(
        {"name": "helper", "change_type": "modified", "start_line": 10, "end_line": 15}
    )
    graph = build_evidence_graph(enriched_files=enriched)
    helper_node = next(n for n in graph if n["symbol"] == "helper")
    assert "main" in helper_node["signals"]["called_by"]


# ---------------------------------------------------------------------------
# 7. imports signal
# ---------------------------------------------------------------------------

def test_imports_from_full_content() -> None:
    """Module imports are extracted from full file content via AST."""
    full_content = '''
import os
import json
from stripe import charge
from services.tax import calculate
'''
    enriched = [_enriched_file(
        "src/service.py",
        ["x = 1"],
        ["my_func"],
        full_content=full_content,
    )]
    graph = build_evidence_graph(enriched_files=enriched)
    node = next(n for n in graph if n["symbol"] == "my_func")
    assert "os" in node["signals"]["imports"]
    assert "json" in node["signals"]["imports"]
    assert "stripe" in node["signals"]["imports"]
    assert "services.tax" in node["signals"]["imports"]


def test_imports_empty_without_full_content() -> None:
    """Without full_content, imports list is empty."""
    enriched = [_enriched_file(
        "src/service.py",
        ["x = 1"],
        ["my_func"],
    )]
    graph = build_evidence_graph(enriched_files=enriched)
    node = next(n for n in graph if n["symbol"] == "my_func")
    assert node["signals"]["imports"] == []


def test_imports_with_syntax_error() -> None:
    """Malformed full_content produces empty imports (no crash)."""
    enriched = [_enriched_file(
        "src/service.py",
        ["x = 1"],
        ["my_func"],
        full_content="def {{{ invalid python",
    )]
    graph = build_evidence_graph(enriched_files=enriched)
    node = next(n for n in graph if n["symbol"] == "my_func")
    assert node["signals"]["imports"] == []


# ---------------------------------------------------------------------------
# 8. change_type propagation
# ---------------------------------------------------------------------------

def test_change_type_preserved() -> None:
    """change_type from changed_functions is preserved in evidence node."""
    enriched = [_enriched_file(
        "src/service.py",
        ["x = 1"],
        ["new_func"],
        change_types=["added"],
    )]
    graph = build_evidence_graph(enriched_files=enriched)
    node = next(n for n in graph if n["symbol"] == "new_func")
    assert node["change_type"] == "added"


def test_change_type_default_modified() -> None:
    """Missing change_type defaults to 'modified'."""
    enriched = [_enriched_file(
        "src/service.py",
        ["x = 1"],
        ["my_func"],
    )]
    graph = build_evidence_graph(enriched_files=enriched)
    node = next(n for n in graph if n["symbol"] == "my_func")
    assert node["change_type"] == "modified"


# ---------------------------------------------------------------------------
# 9. EvidenceNode / SymbolSignals dataclasses
# ---------------------------------------------------------------------------

def test_evidence_node_to_dict() -> None:
    """EvidenceNode.to_dict produces the expected schema."""
    node = EvidenceNode(
        symbol="checkout",
        file="src/checkout.py",
        change_type="modified",
        signals=SymbolSignals(
            is_entrypoint=True,
            is_io=False,
            writes_state=True,
            reads_state=["cache:user"],
            calls=["calculate_tax"],
            called_by=["main"],
            imports=["stripe"],
        ),
    )
    d = node.to_dict()
    assert d["symbol"] == "checkout"
    assert d["signals"]["is_entrypoint"] is True
    assert d["signals"]["writes_state"] is True
    assert d["signals"]["reads_state"] == ["cache:user"]
    assert d["signals"]["calls"] == ["calculate_tax"]
    assert d["signals"]["called_by"] == ["main"]
    assert d["signals"]["imports"] == ["stripe"]


def test_symbol_signals_defaults() -> None:
    """SymbolSignals defaults are correct."""
    s = SymbolSignals()
    assert s.is_entrypoint is False
    assert s.is_io is False
    assert s.writes_state is False
    assert s.reads_state == []
    assert s.calls == []
    assert s.called_by == []
    assert s.imports == []


# ---------------------------------------------------------------------------
# 10. Integration: combined signals on a realistic symbol
# ---------------------------------------------------------------------------

def test_realistic_symbol_signals() -> None:
    """A realistic checkout function gets all signals correctly."""
    full_content = '''
import stripe
from services.tax import calculate_tax

@router.post("/checkout")
async def checkout(order):
    tax = calculate_tax(order)
    result = stripe.charge(amount=order.total + tax)
    cache.set("last_order", result)
    return result
'''
    enriched = [_enriched_file(
        "src/checkout/service.py",
        [
            "tax = calculate_tax(order)",
            'result = stripe.charge(amount=order.total + tax)',
            'cache.set("last_order", result)',
            "return result",
        ],
        ["checkout"],
        endpoints=[{"function": "checkout", "route": "/checkout", "method": "POST"}],
        full_content=full_content,
    )]
    graph = build_evidence_graph(enriched_files=enriched)
    node = next(n for n in graph if n["symbol"] == "checkout")

    # Entrypoint: yes (from endpoints)
    assert node["signals"]["is_entrypoint"] is True

    # State writes: yes (cache.set)
    assert node["signals"]["writes_state"] is True

    # Imports: stripe, services.tax
    assert "stripe" in node["signals"]["imports"]
    assert "services.tax" in node["signals"]["imports"]

    # Calls: should include calculate_tax
    assert "calculate_tax" in node["signals"]["calls"]

    # change_type
    assert node["change_type"] == "modified"

    # File
    assert node["file"] == "src/checkout/service.py"
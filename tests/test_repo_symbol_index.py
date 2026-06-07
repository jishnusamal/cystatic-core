"""Tests for the RepositorySymbolIndex (Task H — repo-wide symbol index).

These tests verify:
  1. RepositorySymbolIndex.from_files() extracts function/method names from
     Python source via AST.
  2. It extracts FastAPI and Flask endpoints.
  3. CausalGraphBuilder.build() expands `known_symbols` when a repo index
     is supplied, so calls to unchanged repo functions produce real edges.
  4. ALL endpoints from the index are registered as typed nodes, not just
     the ones in the diff.
  5. Defensive handling of malformed input does not crash the pipeline.
"""

from __future__ import annotations

from core_engine.causal_graph import (
    CausalGraphBuilder,
    RepositorySymbolIndex,
    build_causal_graph,
)


# ----- 1. Index extraction ----------------------------------------------------

def test_repo_index_extracts_function_names() -> None:
    files = [
        (
            "src/billing/service.py",
            "def compute_total(items):\n    return sum(items)\n\n"
            "async def refund(order_id):\n    return order_id\n",
        ),
        (
            "src/orders/service.py",
            "def place_order(cart):\n    return None\n",
        ),
    ]
    idx = RepositorySymbolIndex.from_files(files)
    # dunders excluded, real functions included
    assert "compute_total" in idx.known_symbols
    assert "refund" in idx.known_symbols
    assert "place_order" in idx.known_symbols
    assert "__init__" not in idx.known_symbols
    # file_symbols is populated
    assert "src/billing/service.py" in idx.file_symbols
    assert "compute_total" in idx.file_symbols["src/billing/service.py"]


def test_repo_index_extracts_fastapi_endpoints() -> None:
    files = [
        (
            "src/api/users.py",
            "from fastapi import APIRouter\n"
            "router = APIRouter()\n\n"
            "@router.get('/users')\n"
            "async def list_users():\n    return []\n\n"
            "@router.post('/users')\n"
            "def create_user():\n    return None\n",
        ),
    ]
    idx = RepositorySymbolIndex.from_files(files)
    routes = {ep["route"] for ep in idx.all_endpoints}
    assert "/users" in routes
    methods = {ep["method"] for ep in idx.all_endpoints if ep["route"] == "/users"}
    assert methods == {"GET", "POST"}


def test_repo_index_extracts_flask_endpoints() -> None:
    files = [
        (
            "src/api/auth.py",
            "from flask import Flask\n"
            "app = Flask(__name__)\n\n"
            "@app.route('/login', methods=['GET', 'POST'])\n"
            "def login():\n    return ''\n",
        ),
    ]
    idx = RepositorySymbolIndex.from_files(files)
    routes = {ep["route"] for ep in idx.all_endpoints}
    assert "/login" in routes
    login_ep = next(ep for ep in idx.all_endpoints if ep["route"] == "/login")
    # Flask with explicit methods
    assert "GET" in login_ep["method"]
    assert "POST" in login_ep["method"]


def test_repo_index_handles_syntax_errors_defensively() -> None:
    files = [
        ("broken.py", "def broken(:\n    pass\n"),  # SyntaxError
        ("good.py", "def fine():\n    return 1\n"),
    ]
    # Should NOT raise — broken file is silently skipped
    idx = RepositorySymbolIndex.from_files(files)
    assert "fine" in idx.known_symbols
    # Broken file is tracked but with empty symbol set
    assert "broken.py" in idx.file_symbols
    assert idx.file_symbols["broken.py"] == set()


def test_repo_index_skips_invalid_inputs() -> None:
    files = [
        ("", "def f(): pass"),  # empty path
        (None, "def g(): pass"),  # type: ignore[arg-type]
        ("ok.py", ""),  # empty content
    ]
    idx = RepositorySymbolIndex.from_files(files)  # type: ignore[arg-type]
    # No crash, no garbage
    assert isinstance(idx.known_symbols, set)


def test_repo_index_merge_combines() -> None:
    a = RepositorySymbolIndex.from_files([("a.py", "def alpha(): pass")])
    b = RepositorySymbolIndex.from_files([("b.py", "def beta(): pass")])
    a.merge(b)
    assert "alpha" in a.known_symbols
    assert "beta" in a.known_symbols


def test_repo_index_is_known_helper() -> None:
    idx = RepositorySymbolIndex.from_files([("m.py", "def known_thing(): pass")])
    assert idx.is_known("known_thing") is True
    assert idx.is_known("not_defined") is False


def test_repo_index_stats() -> None:
    idx = RepositorySymbolIndex.from_files([
        ("a.py", "@router.get('/x')\ndef a(): pass"),
        ("b.py", "def b(): pass\ndef c(): pass"),
    ])
    s = idx.stats()
    assert s["known_symbol_count"] >= 3
    assert s["endpoint_count"] >= 1
    assert s["indexed_file_count"] == 2


# ----- 2. CausalGraphBuilder integration --------------------------------------

def test_build_with_no_index_is_diff_only() -> None:
    """No index: known_symbols = changed functions only. Calls to unchanged
    helpers do NOT produce edges."""
    enriched = [
        {
            "file_path": "src/billing/service.py",
            "hunks": [
                {
                    "lines": [
                        {"line_type": "added", "content": "result = _helper()"},
                    ]
                }
            ],
            "changed_functions": [
                {"name": "src.billing.service.compute_total", "start_line": 1, "end_line": 2},
            ],
        }
    ]
    g = build_causal_graph(enriched_files=enriched)
    # `_helper` is NOT a known symbol (not in changed_functions)
    # so no edge is created.
    has_helper_edge = any(
        e.to_symbol == "_helper" for e in g.edges
    )
    assert has_helper_edge is False


def test_build_with_index_expands_known_symbols() -> None:
    """With index: `_helper` is a known repo symbol, so the call produces a
    real edge — this is the unlock for cross-boundary propagation."""
    enriched = [
        {
            "file_path": "src/billing/service.py",
            "hunks": [
                {
                    "lines": [
                        {"line_type": "added", "content": "result = _helper()"},
                    ]
                }
            ],
            "changed_functions": [
                {"name": "src.billing.service.compute_total", "start_line": 1, "end_line": 2},
            ],
        }
    ]
    # `_helper` is defined elsewhere in the repo (unchanged)
    repo_index = RepositorySymbolIndex.from_files([
        ("src/billing/helpers.py", "def _helper():\n    return 1\n"),
    ])

    g = build_causal_graph(enriched_files=enriched, repo_index=repo_index)
    # Now `_helper` IS known — the call produces a calls edge
    has_helper_edge = any(
        e.to_symbol == "_helper" and e.edge_type == "calls"
        for e in g.edges
    )
    assert has_helper_edge is True, (
        "expected a 'calls' edge to _helper when repo_index is provided; "
        f"got edges: {[(e.from_symbol, e.to_symbol, e.edge_type) for e in g.edges]}"
    )


def test_build_with_index_registers_all_endpoints() -> None:
    """With index: ALL endpoints from the index are registered as nodes,
    not just the ones in the diff."""
    enriched = [
        {
            "file_path": "src/api/users.py",
            "hunks": [
                {
                    "lines": [
                        {"line_type": "added", "content": "@router.get('/changed')"},
                        {"line_type": "added", "content": "def changed_handler(): pass"},
                    ]
                }
            ],
            "changed_functions": [
                {"name": "changed_handler", "start_line": 1, "end_line": 2},
            ],
            "endpoints": [
                {"route": "/changed", "method": "GET", "function": "changed_handler"},
            ],
        }
    ]
    # Index has TWO endpoints, only one of which is in the diff
    repo_index = RepositorySymbolIndex.from_files([
        (
            "src/api/users.py",
            "@router.get('/changed')\ndef changed_handler(): pass\n\n"
            "@router.post('/unchanged')\ndef unchanged_handler(): pass\n",
        ),
    ])

    g = build_causal_graph(enriched_files=enriched, repo_index=repo_index)
    routes = {
        n.metadata.get("function") or n.name
        for n in g.nodes.values() if n.node_type == "endpoint"
    }
    # /changed is in diff AND in index
    assert "/changed" in {n.name for n in g.nodes.values() if n.node_type == "endpoint"}
    # /unchanged is NOT in diff but IS in the index — must still be registered
    assert "/unchanged" in {n.name for n in g.nodes.values() if n.node_type == "endpoint"}


def test_build_with_no_index_unchanged_endpoints_not_registered() -> None:
    """Sanity: WITHOUT the index, only diff-local endpoints are visible."""
    enriched = [
        {
            "file_path": "src/api/users.py",
            "hunks": [
                {
                    "lines": [
                        {"line_type": "added", "content": "@router.get('/changed')"},
                        {"line_type": "added", "content": "def changed_handler(): pass"},
                    ]
                }
            ],
            "changed_functions": [
                {"name": "changed_handler", "start_line": 1, "end_line": 2},
            ],
            "endpoints": [
                {"route": "/changed", "method": "GET", "function": "changed_handler"},
            ],
        }
    ]
    g = build_causal_graph(enriched_files=enriched)  # no repo_index
    routes = {n.name for n in g.nodes.values() if n.node_type == "endpoint"}
    assert "/changed" in routes
    # The other endpoint would be at /unchanged — but it's NOT in the diff
    # and there's no index, so it shouldn't appear.
    assert "/unchanged" not in routes


def test_build_with_empty_index_is_safe() -> None:
    """Defensive: an empty index must not break the build."""
    enriched = [
        {
            "file_path": "src/a.py",
            "hunks": [
                {"lines": [{"line_type": "added", "content": "x = 1"}]}
            ],
            "changed_functions": [
                {"name": "foo", "start_line": 1, "end_line": 1},
            ],
        }
    ]
    g = build_causal_graph(enriched_files=enriched, repo_index=RepositorySymbolIndex())
    assert g is not None


def test_build_index_expands_known_symbols_does_not_replace() -> None:
    """The expansion is additive: diff-changed functions PLUS index symbols
    are BOTH known. Neither set replaces the other."""
    enriched = [
        {
            "file_path": "src/a.py",
            "hunks": [
                {
                    "lines": [
                        {"line_type": "added", "content": "x = changed_only_thing()"},
                        {"line_type": "added", "content": "y = repo_only_thing()"},
                    ]
                }
            ],
            "changed_functions": [
                {"name": "changed_only_thing", "start_line": 1, "end_line": 1},
            ],
        }
    ]
    repo_index = RepositorySymbolIndex.from_files([
        ("src/b.py", "def repo_only_thing(): return 1\n"),
    ])
    g = build_causal_graph(enriched_files=enriched, repo_index=repo_index)
    called = {e.to_symbol for e in g.edges}
    assert "changed_only_thing" in called  # diff-known
    assert "repo_only_thing" in called  # index-known

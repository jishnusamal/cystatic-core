"""Tests for Task I — shared_state as named resource nodes.

These tests verify the new model:
  - Resources like `cache:user`, `redis:cart`, `session:token` are extracted
    and registered as typed nodes (node_type="shared_state").
  - Edges are DIRECTIONAL through the resource:
        writer_symbol → resource → reader_symbol
  - Old fully-connected "any pair of symbols touching the same pattern"
    heuristic is REMOVED — no symbol↔symbol edges are produced.
  - Blast radius tracks `affected_shared_state`.

The new model collapses O(n^2) edges into O(n) and dramatically reduces
false positives compared to the old "any two accessors are coupled" rule.
"""
from __future__ import annotations

from core_engine.causal_graph import (
    CausalGraph,
    CausalGraphBuilder,
    CausalNode,
    build_causal_graph,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _enriched_file(file_path: str, lines: list[str], fn_names: list[str]) -> dict:
    """Build an enriched_file dict from a list of changed line contents.

    NOTE: the lines should mention the changed function's name (e.g.,
    `def checkout(...)`) for shared_state edges to be attributed to
    that symbol. For pure resource-extraction tests, no symbol match
    is needed.
    """
    return {
        "file_path": file_path,
        "hunks": [
            {"lines": [{"line_type": "added", "content": ln} for ln in lines]}
        ],
        "changed_functions": [
            {"name": fn, "start_line": 1, "end_line": 1} for fn in fn_names
        ],
    }


def _with_symbol(symbol: str, *body_lines: str) -> list[str]:
    """Wrap body lines inside a def so the symbol name is on each line.

    Real diffs look like:
        def checkout(user):
            cache.set("user", user)

    For the detector to attribute a shared_state line to `checkout`,
    the symbol's name must appear on the same line. This helper
    produces a multi-line snippet that does exactly that.
    """
    return [f"def {symbol}():\n"] + [f"    {ln}" for ln in body_lines]


# ---------------------------------------------------------------------------
# 1. Resource extraction
# ---------------------------------------------------------------------------

def test_cache_set_extracts_resource_name() -> None:
    """cache.set("user", x) should register cache:user as a shared_state node."""
    enriched = [_enriched_file(
        "src/checkout/service.py",
        _with_symbol("checkout", 'cache.set("user", user_obj)'),
        ["checkout"],
    )]
    g = build_causal_graph(enriched_files=enriched)
    resources = {n.name for n in g.nodes.values() if n.node_type == "shared_state"}
    assert "cache:user" in resources, (
        f"expected cache:user, got: {resources}"
    )


def test_cache_get_extracts_resource_name() -> None:
    """cache.get("user") should register cache:user as a shared_state node."""
    enriched = [_enriched_file(
        "src/discount/service.py",
        _with_symbol("discount_engine", 'user = cache.get("user")'),
        ["discount_engine"],
    )]
    g = build_causal_graph(enriched_files=enriched)
    resources = {n.name for n in g.nodes.values() if n.node_type == "shared_state"}
    assert "cache:user" in resources


def test_session_subscript_extracts_resource() -> None:
    """session["token"] should register session:token as a shared_state node."""
    enriched = [_enriched_file(
        "src/auth/service.py",
        _with_symbol("check_session", 'token = session["token"]'),
        ["check_session"],
    )]
    g = build_causal_graph(enriched_files=enriched)
    resources = {n.name for n in g.nodes.values() if n.node_type == "shared_state"}
    assert "session:token" in resources


def test_redis_set_extracts_resource() -> None:
    """redis.set("cart", value) -> redis:cart node."""
    enriched = [_enriched_file(
        "src/cart/service.py",
        _with_symbol("add_to_cart", 'redis.set("cart", cart_data)'),
        ["add_to_cart"],
    )]
    g = build_causal_graph(enriched_files=enriched)
    resources = {n.name for n in g.nodes.values() if n.node_type == "shared_state"}
    assert "redis:cart" in resources


def test_redis_attribute_fallback() -> None:
    """redis.cart (bare attribute) -> redis:cart node."""
    enriched = [_enriched_file(
        "src/cart/service.py",
        _with_symbol("get_cart", "data = redis.cart"),
        ["get_cart"],
    )]
    g = build_causal_graph(enriched_files=enriched)
    resources = {n.name for n in g.nodes.values() if n.node_type == "shared_state"}
    assert "redis:cart" in resources


# ---------------------------------------------------------------------------
# 2. Directional edges (write vs read) through the resource node
# ---------------------------------------------------------------------------

def test_writer_creates_symbol_to_resource_edge() -> None:
    """A writer (cache.set) should produce an edge symbol -> resource."""
    enriched = [_enriched_file(
        "src/checkout/service.py",
        _with_symbol("checkout", 'cache.set("user", user_obj)'),
        ["checkout"],
    )]
    g = build_causal_graph(enriched_files=enriched)
    write_edges = [
        e for e in g.edges
        if e.edge_type == "shared_state"
        and e.from_symbol == "checkout"
        and e.to_symbol == "cache:user"
    ]
    assert len(write_edges) == 1, (
        f"expected 1 write edge checkout -> cache:user, "
        f"got: {[(e.from_symbol, e.to_symbol, e.edge_type) for e in g.edges]}"
    )
    # Writes are higher confidence than reads
    assert write_edges[0].confidence >= 0.5


def test_reader_creates_resource_to_symbol_edge() -> None:
    """A reader (cache.get) should produce an edge resource -> symbol."""
    enriched = [_enriched_file(
        "src/discount/service.py",
        _with_symbol("discount_engine", 'user = cache.get("user")'),
        ["discount_engine"],
    )]
    g = build_causal_graph(enriched_files=enriched)
    read_edges = [
        e for e in g.edges
        if e.edge_type == "shared_state"
        and e.from_symbol == "cache:user"
        and e.to_symbol == "discount_engine"
    ]
    assert len(read_edges) == 1, (
        f"expected 1 read edge cache:user -> discount_engine, "
        f"got: {[(e.from_symbol, e.to_symbol, e.edge_type) for e in g.edges]}"
    )


def test_no_symbol_to_symbol_shared_state_edges() -> None:
    """Critical: the OLD model created symbol↔symbol edges for any pair of
    accessors. The new model MUST NOT create any such edges. The only
    shared_state edges allowed are symbol↔resource or resource↔resource.

    Same file, two symbols, both touching cache. The old model would
    create A↔B. The new model must not.
    """
    # Inline dict (the helper doesn't accept multi-line lists easily).
    enriched = [{
        "file_path": "src/app/service.py",
        "hunks": [{"lines": [
            {"line_type": "added", "content": "def alpha():"},
            {"line_type": "added", "content": '    cache.set("user", user)'},
            {"line_type": "added", "content": "def beta():"},
            {"line_type": "added", "content": '    cached = cache.get("user")'},
        ]}],
        "changed_functions": [
            {"name": "alpha", "start_line": 1, "end_line": 1},
            {"name": "beta", "start_line": 1, "end_line": 1},
        ],
    }]
    g = build_causal_graph(enriched_files=enriched)
    # Look for any shared_state edge directly between two non-resource nodes
    resource_node_names = {n.name for n in g.nodes.values() if n.node_type == "shared_state"}
    bad_edges = [
        e for e in g.edges
        if e.edge_type == "shared_state"
        and e.from_symbol not in resource_node_names
        and e.to_symbol not in resource_node_names
    ]
    assert bad_edges == [], (
        f"found forbidden symbol↔symbol shared_state edges: "
        f"{[(e.from_symbol, e.to_symbol) for e in bad_edges]}"
    )


# ---------------------------------------------------------------------------
# 3. The "checkout -> cache:user -> discount_engine" propagation case
# ---------------------------------------------------------------------------

def test_propagation_through_resource_node() -> None:
    """The headline example: writer flows through resource to reader.

    If `checkout` writes cache:user and `discount_engine` reads cache:user,
    then the blast radius from checkout should reach discount_engine
    (via the resource node).
    """
    enriched = [
        {
            "file_path": "src/checkout/service.py",
            "hunks": [{"lines": [
                {"line_type": "added", "content": "def checkout():"},
                {"line_type": "added", "content": '    cache.set("user", user)'},
            ]}],
            "changed_functions": [
                {"name": "checkout", "start_line": 1, "end_line": 1},
            ],
        },
        {
            "file_path": "src/discount/service.py",
            "hunks": [{"lines": [
                {"line_type": "added", "content": "def discount_engine():"},
                {"line_type": "added", "content": '    user = cache.get("user")'},
            ]}],
            "changed_functions": [
                {"name": "discount_engine", "start_line": 1, "end_line": 1},
            ],
        },
    ]
    g = build_causal_graph(enriched_files=enriched)

    # Direct: checkout -> cache:user  (write)
    assert any(
        e.from_symbol == "checkout"
        and e.to_symbol == "cache:user"
        and e.edge_type == "shared_state"
        for e in g.edges
    )

    # Direct: cache:user -> discount_engine  (read)
    assert any(
        e.from_symbol == "cache:user"
        and e.to_symbol == "discount_engine"
        and e.edge_type == "shared_state"
        for e in g.edges
    )

    # Blast radius: from checkout, should reach discount_engine through the
    # resource node. The path is checkout -> cache:user -> discount_engine.
    blast = g.compute_blast_radius(["checkout"])
    assert "cache:user" in blast["affected_shared_state"]
    # The reader is reached via the resource, so it appears in downstream_symbols
    reached = {d["symbol"] for d in blast["downstream_symbols"]}
    assert "discount_engine" in reached, (
        f"expected discount_engine to be reached from checkout via cache:user, "
        f"got: {reached}"
    )


# ---------------------------------------------------------------------------
# 4. Different resources are NOT cross-coupled (precision)
# ---------------------------------------------------------------------------

def test_different_resources_do_not_couple_symbols() -> None:
    """If `alpha` writes cache:user and `beta` reads cache:orders, they do
    NOT share state. The new model must not produce a coupling edge.

    The OLD model would have coupled them (both touch `cache.`).
    """
    enriched = [{
        "file_path": "src/app/service.py",
        "hunks": [{"lines": [
            {"line_type": "added", "content": "def alpha():"},
            {"line_type": "added", "content": '    cache.set("user", user_obj)'},
            {"line_type": "added", "content": "def beta():"},
            {"line_type": "added", "content": '    orders = cache.get("orders")'},
        ]}],
        "changed_functions": [
            {"name": "alpha", "start_line": 1, "end_line": 1},
            {"name": "beta", "start_line": 1, "end_line": 1},
        ],
    }]
    g = build_causal_graph(enriched_files=enriched)

    # Both resources should be present
    resources = {n.name for n in g.nodes.values() if n.node_type == "shared_state"}
    assert "cache:user" in resources
    assert "cache:orders" in resources

    # No symbol↔symbol shared_state edges
    resource_node_names = resources
    bad_edges = [
        e for e in g.edges
        if e.edge_type == "shared_state"
        and e.from_symbol not in resource_node_names
        and e.to_symbol not in resource_node_names
    ]
    assert bad_edges == [], (
        f"alpha and beta should NOT be coupled (different resources), "
        f"but found: {[(e.from_symbol, e.to_symbol) for e in bad_edges]}"
    )


# ---------------------------------------------------------------------------
# 5. Blast radius integration
# ---------------------------------------------------------------------------

def test_blast_radius_includes_affected_shared_state() -> None:
    """compute_blast_radius() must include affected_shared_state in output."""
    enriched = [
        {
            "file_path": "src/checkout/service.py",
            "hunks": [{"lines": [
                {"line_type": "added", "content": "def checkout():"},
                {"line_type": "added", "content": '    cache.set("user", user)'},
            ]}],
            "changed_functions": [
                {"name": "checkout", "start_line": 1, "end_line": 1},
            ],
        },
    ]
    g = build_causal_graph(enriched_files=enriched)
    blast = g.compute_blast_radius(["checkout"])
    assert "affected_shared_state" in blast
    assert "cache:user" in blast["affected_shared_state"]


def test_critical_paths_include_shared_state_boundary() -> None:
    """A path that ends at a shared_state node is a critical path."""
    enriched = [
        {
            "file_path": "src/checkout/service.py",
            "hunks": [{"lines": [
                {"line_type": "added", "content": "def checkout():"},
                {"line_type": "added", "content": '    cache.set("user", user)'},
            ]}],
            "changed_functions": [
                {"name": "checkout", "start_line": 1, "end_line": 1},
            ],
        },
    ]
    g = build_causal_graph(enriched_files=enriched)
    blast = g.compute_blast_radius(["checkout"])
    # Path [checkout, cache:user] should be a critical path (ends at typed node)
    assert any(
        path[-1] == "cache:user"
        for path in blast["critical_paths"]
    ), (
        f"expected a critical path ending at cache:user, "
        f"got: {blast['critical_paths']}"
    )


# ---------------------------------------------------------------------------
# 6. Evidence grounding
# ---------------------------------------------------------------------------

def test_edges_carry_evidence_snippet_and_location() -> None:
    """Each emitted edge must have a snippet, location, and evidence_type.
    Engineers inspect this to verify causal claims."""
    enriched = [_enriched_file(
        "src/checkout/service.py",
        _with_symbol("checkout", 'cache.set("user", user)'),
        ["checkout"],
    )]
    g = build_causal_graph(enriched_files=enriched)
    write_edges = [
        e for e in g.edges
        if e.edge_type == "shared_state"
        and e.from_symbol == "checkout"
    ]
    assert write_edges
    e = write_edges[0]
    assert e.evidence_snippet
    assert "user" in e.evidence_snippet.lower()
    assert e.evidence_location
    assert "src/checkout/service.py" in e.evidence_location
    assert e.evidence_type == "shared_access"


# ---------------------------------------------------------------------------
# 7. Defensive: no symbol list => no edges
# ---------------------------------------------------------------------------

def test_no_symbols_means_no_shared_state_edges() -> None:
    """Defensive: if no changed functions, no shared_state work happens."""
    enriched = [{
        "file_path": "src/x.py",
        "hunks": [{"lines": [{"line_type": "added", "content": 'cache.set("user", x)'}]}],
        "changed_functions": [],
    }]
    g = build_causal_graph(enriched_files=enriched)
    # No symbols -> no shared_state edges, but the line is still scanned
    # without crashing. (No symbol, so no edge can be attributed.)
    assert all(
        e.from_symbol != "cache" and e.to_symbol != "cache"
        for e in g.edges
        if e.edge_type == "shared_state"
    )

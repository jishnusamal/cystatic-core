"""
Causal Graph Engine — NON-NEGOTIABLE core primitive.

Builds a directed graph of symbol-to-symbol relationships:
  from: "symbol A"
  to: "symbol B"
  type: "data_flow | control_flow | shared_state | async_event | db_dependency | transaction_boundary"
  confidence: 0.0 - 1.0

This turns "diff understanding" into "system simulation".
"""
from __future__ import annotations

import ast
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


# Test/mock function prefixes — symbols matching these are excluded from
# the causal graph and change influence pipeline. They are noise, not
# production-relevant symbols.
_TEST_FN_PREFIXES: tuple[str, ...] = (
    "test_", "_test", "mock_", "fixture_", "stub_", "fake_", "dummy_"
)

# Phase 3: Domain hub constants — synthetic aggregation nodes that collapse
# N² cross-domain edges into 2N hub edges.
# Example: instead of 20 checkout symbols × 20 tax symbols = 400 edges,
# we get 20 checkout → DOMAIN_CHECKOUT + 20 tax → DOMAIN_TAX + 1 hub edge = 41 edges.
_DOMAIN_HUB_NAMES: tuple[str, ...] = (
    "DOMAIN_CHECKOUT",
    "DOMAIN_ORDER",
    "DOMAIN_INVOICE",
    "DOMAIN_PAYMENT",
    "DOMAIN_TAX",
    "DOMAIN_WALLET",
    "DOMAIN_BILLING",
    "DOMAIN_AUTH",
    "DOMAIN_NOTIFICATION",
    "DOMAIN_FULFILLMENT",
    "DOMAIN_INVENTORY",
    "DOMAIN_CATALOG",
)

# Mapping from domain keywords to hub names
_DOMAIN_TO_HUB: dict[str, str] = {
    "checkout": "DOMAIN_CHECKOUT",
    "order": "DOMAIN_ORDER",
    "invoice": "DOMAIN_INVOICE",
    "payment": "DOMAIN_PAYMENT",
    "tax": "DOMAIN_TAX",
    "wallet": "DOMAIN_WALLET",
    "billing": "DOMAIN_BILLING",
    "auth": "DOMAIN_AUTH",
    "notification": "DOMAIN_NOTIFICATION",
    "fulfillment": "DOMAIN_FULFILLMENT",
    "inventory": "DOMAIN_INVENTORY",
    "catalog": "DOMAIN_CATALOG",
}

# Phase 3: Typed edge weights for propagation scoring.
# These override raw confidence when set on CausalEdge.edge_weight.
_EDGE_TYPE_WEIGHTS: dict[str, float] = {
    "calls": 1.0,
    "called_by": 0.9,
    "data_flow": 0.9,
    "shared_state": 0.8,
    "async_event": 0.7,
    "db_dependency": 0.7,
    "transaction_boundary": 0.85,
    "control_flow": 0.6,
    # Phase 3: Domain hub edges
    "domain": 0.4,
}


def _is_test_or_mock_symbol(symbol: str) -> bool:
    """Check if a symbol name indicates a test, mock, or fixture function."""
    lowered = symbol.lower()
    return any(lowered.startswith(prefix) or lowered.endswith(prefix.rstrip("_"))
               for prefix in _TEST_FN_PREFIXES)


@dataclass
class SymbolSignals:
    """Lightweight behavioral signals for a symbol, extracted via static heuristics.

    This is the "evidence token" layer — not ground truth, but probabilistic
    structure that makes the causal graph actionable.
    """
    is_entrypoint: bool = False
    is_io: bool = False
    writes_state: bool = False
    reads_state: list[str] = field(default_factory=list)
    calls: list[str] = field(default_factory=list)
    called_by: list[str] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)


@dataclass
class EvidenceNode:
    """A grounded node in the evidence graph with behavioral signals.

    The evidence graph is the enriched, grounded version of raw symbols.
    Each node carries probabilistic signals (is_entrypoint, is_io, etc.)
    that downstream consumers (blast radius, propagation) can use for
    richer analysis.
    """
    symbol: str
    file: str
    change_type: str  # "added" | "modified" | "deleted"
    signals: SymbolSignals = field(default_factory=SymbolSignals)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "file": self.file,
            "change_type": self.change_type,
            "signals": {
                "is_entrypoint": self.signals.is_entrypoint,
                "is_io": self.signals.is_io,
                "writes_state": self.signals.writes_state,
                "reads_state": self.signals.reads_state,
                "calls": self.signals.calls,
                "called_by": self.signals.called_by,
                "imports": self.signals.imports,
            },
        }


@dataclass
class WeakEdge:
    """A weak causal edge with evidence tokens.

    Phase 2 — evidence edges with confidence + type. Every edge MUST have
    at least 1 evidence string. This replaces LLM reasoning with grounded,
    probabilistic structure.

    Edge types (5):
        CALLS              — direct function invocation
        SHARES_STATE       — shared state (cache/redis/session) coupling
        DATA_FLOW          — result flows from one symbol to another
        CONTROL_FLOW       — one symbol gates execution of another
        CONTRACT_DEPENDENCY — import/type annotation coupling
    """
    from_symbol: str
    to_symbol: str
    edge_type: str  # CALLS | SHARES_STATE | DATA_FLOW | CONTROL_FLOW | CONTRACT_DEPENDENCY
    confidence: float = 0.5  # 0.0 – 1.0
    evidence: list[str] = field(default_factory=list)  # ≥1 evidence string required
    file_path: str = ""

    def __post_init__(self) -> None:
        """Defensive: ensure evidence is always a list (never None or str)."""
        if not isinstance(self.evidence, list):
            self.evidence = [str(self.evidence)] if self.evidence else []

    def __hash__(self) -> int:
        return hash((self.from_symbol, self.to_symbol, self.edge_type))

    def __eq__(self, other: object) -> bool:
        """Equality by (from, to, type) only — matching __hash__."""
        if not isinstance(other, WeakEdge):
            return NotImplemented
        return (
            self.from_symbol == other.from_symbol
            and self.to_symbol == other.to_symbol
            and self.edge_type == other.edge_type
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "from": self.from_symbol,
            "to": self.to_symbol,
            "type": self.edge_type,
            "confidence": round(self.confidence, 3),
            "evidence": self.evidence,
            "file_path": self.file_path,
        }


@dataclass
class CausalEdge:
    """A directed edge in the causal graph with typed edge weights."""
    from_symbol: str
    to_symbol: str
    edge_type: str  # data_flow | control_flow | shared_state | async_event | db_dependency | transaction_boundary
    confidence: float = 0.7  # 0.0 - 1.0
    evidence: str = ""
    file_path: str = ""

    # Evidence grounding — engineers can inspect the source
    evidence_type: str = ""  # "function_call" | "assignment" | "return" | "shared_access" | "db_operation" | "async_emit" | "transaction_boundary" | "import_reference"
    evidence_location: str = ""  # "file/path.py:42"
    evidence_snippet: str = ""  # Actual code line that produced the edge

    # Phase 3: Typed edge weights for propagation scoring
    # EDGE_CALL = 1.0, EDGE_STATE = 0.9, EDGE_IMPORT = 0.6, EDGE_DOMAIN = 0.4
    edge_weight: float = 0.5  # Override weight for propagation scoring

    def __hash__(self) -> int:
        return hash((self.from_symbol, self.to_symbol, self.edge_type))


@dataclass
class CausalNode:
    """A node in the causal graph with type information."""
    name: str
    # Valid types:
    #   Production: "symbol" | "endpoint" | "service" | "database" | "queue"
    #     | "shared_state"
    #   Classification: "runtime" | "test"
    #   Domain hub: "domain_hub"
    # `shared_state` (Task I) represents a named resource like
    # `cache:user`, `redis:cart`, `session:token` — typed so it shows up
    # in blast radius the same way services/endpoints/databases do.
    # `domain_hub` (Phase 3) represents a synthetic domain aggregation node
    # like DOMAIN_CHECKOUT, DOMAIN_PAYMENT, etc.
    node_type: str = "symbol"
    metadata: dict[str, Any] = field(default_factory=dict)

    def __hash__(self) -> int:
        return hash(self.name)


@dataclass
class CausalGraph:
    """The complete causal graph for a PR analysis."""
    edges: list[CausalEdge] = field(default_factory=list)
    nodes: dict[str, CausalNode] = field(default_factory=dict)
    outgoing: dict[str, list[CausalEdge]] = field(default_factory=dict)
    incoming: dict[str, list[CausalEdge]] = field(default_factory=dict)

    def add_edge(self, edge: CausalEdge) -> None:
        self.edges.append(edge)
        self.outgoing.setdefault(edge.from_symbol, []).append(edge)
        self.incoming.setdefault(edge.to_symbol, []).append(edge)
        if edge.from_symbol not in self.nodes:
            self.nodes[edge.from_symbol] = CausalNode(name=edge.from_symbol)
        if edge.to_symbol not in self.nodes:
            self.nodes[edge.to_symbol] = CausalNode(name=edge.to_symbol)

    def get_edge_weight(self, edge: CausalEdge) -> float:
        """Get the effective weight for propagation scoring.

        Phase 3: Uses typed edge weights when available, falls back to confidence.
        """
        if edge.edge_weight != 0.5:  # Non-default weight was set
            return edge.edge_weight
        # Fallback mapping by edge_type
        type_weights = {
            "calls": 1.0,
            "called_by": 0.9,
            "data_flow": 0.9,
            "shared_state": 0.8,
            "async_event": 0.7,
            "db_dependency": 0.7,
            "transaction_boundary": 0.85,
            "control_flow": 0.6,
        }
        return type_weights.get(edge.edge_type, edge.confidence)

    def add_node(self, node: CausalNode) -> None:
        self.nodes[node.name] = node

    def get_outgoing(self, symbol: str) -> list[CausalEdge]:
        """Get all edges originating from symbol."""
        return self.outgoing.get(symbol, [])

    def get_incoming(self, symbol: str) -> list[CausalEdge]:
        """Get all edges terminating at symbol."""
        return self.incoming.get(symbol, [])

    def get_downstream(self, symbol: str, max_hops: int = 5) -> list[tuple[str, float, int]]:
        """
        Get all downstream symbols reachable from the given symbol.
        Returns list of (symbol, propagated_confidence, hop_distance) tuples.

        Phase 3: Uses typed edge weights for propagation scoring.
        """
        downstream: list[tuple[str, float, int]] = []
        visited: set[tuple[str, str]] = set()

        def _traverse(current: str, confidence: float, hops: int) -> None:
            if hops > max_hops:
                return
            for edge in self.get_outgoing(current):
                edge_key = (current, edge.to_symbol)
                if edge_key in visited:
                    continue
                visited.add(edge_key)
                # Phase 3: Use typed edge weight instead of raw confidence
                effective_weight = self.get_edge_weight(edge)
                propagated = confidence * effective_weight
                downstream.append((edge.to_symbol, propagated, hops))
                _traverse(edge.to_symbol, propagated, hops + 1)

        _traverse(symbol, 1.0, 1)
        return downstream

    def compute_blast_radius(
        self,
        changed_symbols: list[str],
        max_hops: int = 5,
        confidence_threshold: float = 0.1,
    ) -> dict[str, Any]:
        """
        Compute blast radius for a set of changed symbols.

        Returns structured output with affected services, endpoints, databases,
        shared-state resources, downstream symbols, and critical paths.

        This is the core product primitive — customers pay for blast radius.

        Phase 3: Uses typed edge weights for propagation scoring.
        """
        affected_services: set[str] = set()
        affected_endpoints: set[str] = set()
        affected_databases: set[str] = set()
        affected_queues: set[str] = set()
        # Task I: shared-state resources (cache:user, redis:cart, session:token)
        # are first-class typed nodes in the blast radius. They show up when a
        # changed symbol writes/reads a resource — making shared-state coupling
        # visible at the same level as services, endpoints, and databases.
        affected_shared_state: set[str] = set()
        downstream_symbols: list[dict[str, Any]] = []
        critical_paths: list[list[str]] = []
        max_confidence = 0.0
        avg_confidence = 0.0
        confidence_count = 0

        visited_edges: set[tuple[str, str]] = set()

        def _traverse(
            current: str,
            path: list[str],
            confidence: float,
            hops: int,
        ) -> None:
            nonlocal max_confidence, avg_confidence, confidence_count
            if hops > max_hops:
                return

            node = self.nodes.get(current)
            if node:
                if node.node_type == "service":
                    affected_services.add(current)
                elif node.node_type == "endpoint":
                    affected_endpoints.add(current)
                elif node.node_type == "database":
                    affected_databases.add(current)
                elif node.node_type == "queue":
                    affected_queues.add(current)
                elif node.node_type == "shared_state":
                    affected_shared_state.add(current)
                # Phase 3: domain_hub nodes are traversal intermediaries, not terminal targets

            for edge in self.get_outgoing(current):
                edge_key = (current, edge.to_symbol)
                if edge_key in visited_edges:
                    continue
                visited_edges.add(edge_key)

                # Phase 3: Use typed edge weight for propagation
                effective_weight = self.get_edge_weight(edge)
                propagated = confidence * effective_weight
                if propagated < confidence_threshold:
                    continue

                max_confidence = max(max_confidence, propagated)
                avg_confidence += propagated
                confidence_count += 1

                downstream_symbols.append({
                    "symbol": edge.to_symbol,
                    "confidence": round(propagated, 3),
                    "hop_distance": hops,
                    "via_edge": edge.edge_type,
                    "evidence_location": edge.evidence_location,
                    "evidence_snippet": edge.evidence_snippet,
                })

                new_path = path + [edge.to_symbol]
                # Record if this path ends at a typed boundary node.
                # shared_state is included — it's a real coupling surface
                # (Task I). domain_hub is excluded — it's an intermediary.
                target_node = self.nodes.get(edge.to_symbol)
                if target_node and target_node.node_type in (
                    "service", "database", "endpoint", "queue", "shared_state",
                ):
                    critical_paths.append(new_path)

                _traverse(edge.to_symbol, new_path, propagated, hops + 1)

        for symbol in changed_symbols:
            _traverse(symbol, [symbol], 1.0, 1)

        avg_confidence = round(avg_confidence / max(confidence_count, 1), 3)

        return {
            "changed_symbols": changed_symbols,
            "blast_radius_score": round(max_confidence, 2),
            "avg_propagation_confidence": avg_confidence,
            "affected_services": sorted(affected_services),
            "affected_endpoints": sorted(affected_endpoints),
            "affected_databases": sorted(affected_databases),
            "affected_queues": sorted(affected_queues),
            "affected_shared_state": sorted(affected_shared_state),
            "downstream_symbols": sorted(
                downstream_symbols,
                key=lambda x: -x["confidence"],
            )[:30],  # cap at 30 for readability
            "critical_paths": critical_paths,
            "total_downstream": len(downstream_symbols),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "edges": [
                {
                    "from": e.from_symbol,
                    "to": e.to_symbol,
                    "type": e.edge_type,
                    "confidence": e.confidence,
                    "evidence": e.evidence,
                    "evidence_type": e.evidence_type,
                    "evidence_location": e.evidence_location,
                    "evidence_snippet": e.evidence_snippet,
                }
                for e in self.edges
            ],
            "nodes": [
                {
                    "name": n.name,
                    "type": n.node_type,
                    "metadata": n.metadata,
                }
                for n in self.nodes.values()
            ],
        }


# -----------------------------------------------------------------------------
# Repository-wide Symbol Index
# -----------------------------------------------------------------------------
# Pre-scans the entire repository (when available) and indexes:
#   - All function/method definitions (the set of "known" symbols)
#   - All route definitions (endpoints) across all files
#   - Which file each symbol lives in
#
# Why this matters (repo-wide symbol index):
#   In diff-only mode we only know the symbols that appear in the diff.
#   That means calls to unchanged repo functions create no edges, and the
#   graph is starved of propagation paths.
#
#   When we have the whole repo (FULL_FILE mode, head SHA archive), we can
#   expand `known_symbols` to include every defined function. Now a call
#   from a changed function to an unchanged helper produces a real edge
#   — and the blast radius can reach the real downstream surface area
#   instead of stopping at the first unseen function.
#
#   net effect: same propagation algorithm, but with the FULL node set,
#   giving a massive quality jump (8.5 -> 9.5).
# -----------------------------------------------------------------------------

_HTTP_METHODS: set[str] = {"get", "post", "put", "delete", "patch", "options", "head"}


def _string_arg(call: "ast.Call", idx: int) -> str | None:
    """Pull a string literal from a Call's positional args (defensive)."""
    if idx < len(call.args):
        arg = call.args[idx]
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            return arg.value
    return None


def _flask_methods(call: "ast.Call") -> list[str]:
    """Extract HTTP methods from a Flask @app.route(methods=[...]) decorator.

    `methods` is stored in the public-facing uppercase form, but the
    membership check is against the lowercase set. Normalize to lowercase
    for the check, then uppercase the output for the consumer.
    """
    for kw in call.keywords:
        if kw.arg != "methods":
            continue
        if isinstance(kw.value, (ast.List, ast.Tuple)):
            out: list[str] = []
            for elt in kw.value.elts:
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                    m = elt.value.lower()
                    if m in _HTTP_METHODS:
                        out.append(m.upper())
            return out
    return []


def _extract_endpoints_from_ast(tree: "ast.AST", file_path: str) -> list[dict]:
    """Lightweight FastAPI/Flask route extractor (defensive — no side effects)."""
    endpoints: list[dict] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            if not isinstance(dec, ast.Call) or not isinstance(dec.func, ast.Attribute):
                continue
            attr = dec.func.attr
            # FastAPI style: @router.get("/path") / @app.post("/path")
            if attr.lower() in _HTTP_METHODS:
                route = _string_arg(dec, 0)
                if route:
                    endpoints.append({
                        "file": file_path,
                        "function": node.name,
                        "method": attr.upper(),
                        "route": route,
                    })
            # Flask style: @app.route("/path", methods=[...])
            elif attr == "route":
                route = _string_arg(dec, 0)
                if route:
                    methods = _flask_methods(dec)
                    endpoints.append({
                        "file": file_path,
                        "function": node.name,
                        "method": ",".join(methods) if methods else "GET",
                        "route": route,
                    })
    return endpoints


def _function_names_from_ast(tree: "ast.AST") -> set[str]:
    """Collect all function/method names defined in a parsed module.

    Skips dunder methods to keep the noise floor low.
    """
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("__") and node.name.endswith("__"):
                continue
            names.add(node.name)
    return names


@dataclass
class RepositorySymbolIndex:
    """Repository-wide symbol index for richer causal graph construction.

    In FULL_FILE mode the orchestrator has access to the head SHA, so it can
    pre-scan the entire repository and build this index. The graph builder
    uses it to expand `known_symbols` and to register ALL endpoints (not just
    the ones in the diff), which dramatically improves blast radius quality.

    In DIFF_ONLY mode this index is not built — the graph falls back to
    diff-only symbol tracking, which is the safe lower bound.
    """
    known_symbols: set[str] = field(default_factory=set)
    all_endpoints: list[dict] = field(default_factory=list)
    file_symbols: dict[str, set[str]] = field(default_factory=dict)
    file_endpoints: dict[str, list[dict]] = field(default_factory=dict)

    @classmethod
    def from_files(cls, files: list[tuple[str, str]]) -> "RepositorySymbolIndex":
        """Build the index from a list of (file_path, content) pairs.

        Decoupled from any specific source adapter. The orchestrator decides
        HOW to obtain the file list (snapshot-by-snapshot, archive extraction,
        tree walk, etc.) and just feeds the pairs in.

        Files that fail to parse are silently skipped (defensive — production
        codebases have malformed files).
        """
        idx = cls()
        for file_path, content in files:
            if not file_path or not isinstance(content, str):
                continue
            try:
                tree = ast.parse(content)
            except SyntaxError:
                idx.file_symbols[file_path] = set()
                continue

            symbols = _function_names_from_ast(tree)
            idx.file_symbols[file_path] = symbols
            idx.known_symbols.update(symbols)

            endpoints = _extract_endpoints_from_ast(tree, file_path)
            if endpoints:
                idx.all_endpoints.extend(endpoints)
                idx.file_endpoints[file_path] = endpoints

        return idx

    def is_known(self, symbol: str) -> bool:
        return symbol in self.known_symbols

    def get_endpoints_for_symbol(self, symbol: str) -> list[dict]:
        return [
            ep for ep in self.all_endpoints
            if ep.get("function") == symbol
        ]

    def merge(self, other: "RepositorySymbolIndex") -> "RepositorySymbolIndex":
        """Merge another index into this one. Returns self for chaining."""
        if other is None:
            return self
        self.known_symbols |= other.known_symbols
        self.all_endpoints.extend(other.all_endpoints)
        for fp, syms in other.file_symbols.items():
            self.file_symbols.setdefault(fp, set()).update(syms)
        for fp, eps in other.file_endpoints.items():
            self.file_endpoints.setdefault(fp, []).extend(eps)
        return self

    def stats(self) -> dict:
        return {
            "known_symbol_count": len(self.known_symbols),
            "endpoint_count": len(self.all_endpoints),
            "indexed_file_count": len(self.file_symbols),
        }


class CausalGraphBuilder:
    """
    Builds a causal graph from enriched file data.

    Inference strategies per edge type:
    - data_flow: A calls B, A assigns to B, A's result feeds B
    - shared_state: writer_symbol → cache:user → reader_symbol (resource as typed node)
    - async_event: A emits event that B consumes (pub/sub, webhooks, queues)
    - db_dependency: A writes what B reads (or vice versa)
    - transaction_boundary: A and B within same atomic unit (DB transaction, etc.)
    """

    # Patterns for detecting call relationships
    CALL_PATTERN = re.compile(r'(?:self\.|\.)?([a-zA-Z_][a-zA-Z0-9_]*)\s*\(')
    DB_ACCESS_PATTERNS = (
        ".save(", ".update(", ".insert(", ".delete(", ".commit(",
        "db.", "database.", "query(", "filter(", "get_or_create(",
    )
    # Split DB patterns into writes vs reads for direction-aware propagation.
    # Writes: symbol → collection. Reads: collection → symbol.
    DB_WRITE_PATTERNS = (
        ".save(", ".update(", ".insert(", ".delete(", ".commit(",
        ".get_or_create(",
    )
    DB_READ_PATTERNS = (
        ".query(", ".filter(",
        "db.", "database.",
    )
    ASYNC_PATTERNS = (
        "queue.", "publish(", "emit(", "dispatch(", "send_task(",
        "webhook.", ".push(", "broker.", "event.",
    )
    # Consumer-side patterns — functions that subscribe to / handle async events.
    # These create edges FROM the event/queue TO the consuming symbol.
    ASYNC_CONSUMER_PATTERNS = (
        "subscribe(", "consumer(", "handler(", "listener(",
        "process_event(", "on_message(", "receive(",
        "handle_event(", "on_event(",
    )
    SHARED_STATE_PATTERNS = (
        "cache.", "redis.", "memcache.", "session.",
        "global_", "singleton", "config.",
        # Bare access forms (no trailing dot) — e.g. session["token"].
        # Match on the backend name with a word boundary or non-word
        # character following. The resource extractor handles the rest.
        "session[",
    )
    # Direction-aware shared_state access patterns. The new model treats
    # shared-state resources (cache:user, redis:cart, session:token) as
    # typed nodes — symbols WRITE to them or READ from them.
    #   Write:  symbol → resource  (e.g., cache.set("user", x))
    #   Read:   resource → symbol  (e.g., x = cache.get("user"))
    # This replaces the old fully-connected "any two symbols touching the
    # same pattern are coupled" heuristic, which was a false-positive
    # factory. Now propagation flows through the actual resource node.
    SHARED_STATE_WRITE_PATTERNS = (
        ".set(", ".put(", ".add(", ".save(", ".update(",
        ".delete(", ".pop(", ".store(", ".write(",
        "session[", "session.",
    )
    SHARED_STATE_READ_PATTERNS = (
        ".get(", ".fetch(", ".read(", ".load(",
        ".peek(", ".retrieve(",
    )
    # Transaction boundary patterns — operations within same atomic block
    TRANSACTION_PATTERNS = (
        "transaction.atomic", "db.session", "begin_transaction",
        "BEGIN;", "START TRANSACTION", "transactional", "@transactional",
    )

    def build(
        self,
        enriched_files: list[dict],
        behavior_diffs: list[Any] | None = None,
        repo_index: RepositorySymbolIndex | None = None,
    ) -> CausalGraph:
        """Build the causal graph from enriched file data.

        Args:
            enriched_files: Diff-only or full-file enriched file data.
            behavior_diffs: Behavior-level deltas (used by the propagation engine).
            repo_index: Optional repository-wide symbol index. When provided
                (FULL_FILE mode with repo access), known_symbols is expanded
                to include every defined function in the repo, and ALL
                endpoints are registered as nodes (not just changed ones).
                This is the Task H repo-wide expansion that dramatically
                improves blast radius quality.
        """
        graph = CausalGraph()

        # Pre-compute ALL symbols defined in the repository.
        # In DIFF_ONLY mode: only changed functions are known.
        # In FULL_FILE mode: the repo index (if provided) contributes the
        # full set of defined functions, so calls to unchanged helpers
        # still produce real edges in the graph.
        self._repo_symbols: set[str] = set()
        for file_data in enriched_files:
            # Track symbols defined in this file (changed functions)
            for fn in file_data.get("changed_functions", []) or []:
                fn_data = self._as_dict(fn)
                name = str(fn_data.get("name", "")).strip()
                if name:
                    symbol = name.split(".")[-1] if "." in name else name
                    # Skip test/mock/fixture symbols — they are noise, not
                    # production-relevant symbols.
                    if _is_test_or_mock_symbol(symbol):
                        continue
                    self._repo_symbols.add(symbol)

        # Store for use by build_evidence_graph() and other post-build methods.
        self._repo_index = repo_index

        # CRITICAL: Only symbols defined in the repository are "known".
        # Imported symbols are NOT treated as dependencies.
        # Imported ≠ executed. Imported ≠ dependency. Imported ≠ impact.
        known_symbols = self._repo_symbols
        if repo_index is not None:
            # Repo-wide expansion: every function defined anywhere in the
            # repo becomes a valid edge target. This is the unlock for
            # propagation reaching past the diff boundary.
            known_symbols = known_symbols | repo_index.known_symbols

        # Phase 3: Collect symbol-to-domain mapping for hub construction
        symbol_domains: dict[str, str] = {}

        for file_data in enriched_files:
            file_path = str(file_data.get("file_path", ""))
            changed_functions = file_data.get("changed_functions", []) or []
            hunks = file_data.get("hunks", []) or []
            hunk_lines = self._collect_lines(hunks)

            # Extract symbols from this file
            file_symbols = self._extract_symbols(changed_functions, file_path)

            # Register service/database/endpoint nodes from keyword signals
            # Pass repo_index so ALL endpoints (not just changed ones) are
            # registered as typed nodes for blast radius computation.
            self._register_typed_nodes(graph, file_data, file_path, repo_index)

            # 1. Detect data_flow/calls edges from function calls — only to KNOWN symbols
            self._detect_call_edges(graph, file_symbols, hunk_lines, file_path, known_symbols)

            # 2. Detect shared_state edges
            self._detect_shared_state_edges(graph, file_symbols, hunk_lines, file_path)

            # 3. Detect async_event edges
            self._detect_async_edges(graph, file_symbols, hunk_lines, file_path)

            # 4. Detect db_dependency edges
            self._detect_db_edges(graph, file_symbols, hunk_lines, file_path)

            # 5. Detect transaction_boundary edges (inside loop — per-file)
            self._detect_transaction_edges(graph, file_symbols, hunk_lines, file_path)

            # Phase 3: Track domain for each symbol
            for symbol in file_symbols:
                domain = self._infer_domain_from_context(symbol, file_path, hunk_lines)
                if domain:
                    symbol_domains[symbol] = domain

        # Phase 3: Build domain hub nodes and connect symbols to hubs
        self._build_domain_hubs(graph, symbol_domains)

        return graph

    def _register_typed_nodes(
        self,
        graph: CausalGraph,
        file_data: dict,
        file_path: str,
        repo_index: RepositorySymbolIndex | None = None,
    ) -> None:
        """Register typed nodes (endpoints, services, databases) from file data.

        When a repo_index is provided (FULL_FILE mode), also registers ALL
        endpoints defined anywhere in the repo — not just the ones in the
        diff. This is critical for blast radius: an unchanged endpoint whose
        handler transitively calls a changed function is a real blast target.
        """
        # Register endpoints (diff-local)
        for ep in file_data.get("endpoints", []) or []:
            ep_name = ep.get("route", "") if isinstance(ep, dict) else str(ep)
            if ep_name:
                graph.add_node(CausalNode(
                    name=ep_name,
                    node_type="endpoint",
                    metadata={"file_path": file_path},
                ))

        # Register ALL repo endpoints when available — this is the unlock
        # for repo-wide blast radius. Without this, only endpoints whose
        # handler is in the diff are visible to the propagation engine.
        if repo_index is not None:
            for ep in repo_index.all_endpoints:
                ep_name = ep.get("route", "")
                if not ep_name:
                    continue
                graph.add_node(CausalNode(
                    name=ep_name,
                    node_type="endpoint",
                    metadata={
                        "file_path": ep.get("file", file_path),
                        "function": ep.get("function", ""),
                        "method": ep.get("method", ""),
                        "from_repo_index": True,
                    },
                ))

        # Infer service names from file path (e.g., services/billing/service.py -> "billing")
        path_parts = file_path.replace("\\", "/").split("/")
        for part in path_parts:
            if any(srv in part.lower() for srv in ("service", "api", "handler", "controller")):
                continue
            # Common service directory names
            if part.lower() in ("billing", "checkout", "payment", "invoice", "auth",
                                "notification", "shipping", "fulfillment", "order", "tax"):
                graph.add_node(CausalNode(
                    name=part.capitalize(),
                    node_type="service",
                    metadata={"file_path": file_path},
                ))

        # Infer database collections from changed lines
        for hunk in file_data.get("hunks", []) or []:
            hunk_data = self._as_dict(hunk)
            for raw_line in hunk_data.get("lines", []) or []:
                line_data = self._as_dict(raw_line)
                content = str(line_data.get("content", "")).strip()
                if content:
                    collection = self._infer_collection(content, "")
                    if collection and not collection.startswith("event_"):
                        graph.add_node(CausalNode(
                            name=collection,
                            node_type="database",
                            metadata={"collection": collection, "file_path": file_path},
                        ))

    def _extract_symbols(
        self,
        changed_functions: list[Any],
        file_path: str,
    ) -> list[str]:
        symbols: list[str] = []
        for fn in changed_functions:
            fn_data = self._as_dict(fn)
            name = str(fn_data.get("name", "")).strip()
            if name:
                symbol = name.split(".")[-1] if "." in name else name
                symbols.append(symbol)
        return symbols

    def _infer_domain_from_context(self, symbol: str, file_path: str, lines: list[str]) -> str | None:
        """Infer the domain of a symbol from file path and code context.

        Phase 3: Used to connect symbols to domain hub nodes.
        """
        # Check file path first (most reliable)
        path_lower = file_path.lower()
        for domain_key in _DOMAIN_TO_HUB:
            if domain_key in path_lower:
                return domain_key

        # Check symbol name
        symbol_lower = symbol.lower()
        for domain_key in _DOMAIN_TO_HUB:
            if domain_key in symbol_lower:
                return domain_key

        # Check code context for domain signals
        for line in lines:
            line_lower = line.lower()
            for domain_key in _DOMAIN_TO_HUB:
                if domain_key in line_lower:
                    return domain_key

        return None

    def _build_domain_hubs(self, graph: CausalGraph, symbol_domains: dict[str, str]) -> None:
        """Build domain hub nodes and connect symbols to their domains.

        Phase 3: This collapses N² cross-domain edges into 2N hub edges.
        Instead of every checkout symbol connecting to every tax symbol,
        each connects to its domain hub, and hubs connect to each other.

        Args:
            graph: The causal graph to augment.
            symbol_domains: Mapping from symbol name to inferred domain.
        """
        # Track which hubs are needed
        hubs_needed: set[str] = set()
        symbol_to_hub: dict[str, str] = {}

        for symbol, domain in symbol_domains.items():
            hub_name = _DOMAIN_TO_HUB.get(domain)
            if hub_name:
                hubs_needed.add(hub_name)
                symbol_to_hub[symbol] = hub_name

        # Register hub nodes (idempotent)
        for hub_name in hubs_needed:
            graph.add_node(CausalNode(
                name=hub_name,
                node_type="domain_hub",
                metadata={"domain": hub_name.replace("DOMAIN_", "").lower()},
            ))

        # Connect symbols to their domain hubs
        for symbol, hub_name in symbol_to_hub.items():
            # Symbol → Hub (outgoing edge)
            graph.add_edge(CausalEdge(
                from_symbol=symbol,
                to_symbol=hub_name,
                edge_type="domain",
                confidence=0.5,
                evidence=f"{symbol} belongs to {hub_name.replace('DOMAIN_', '').lower()} domain",
                file_path="",
                evidence_type="domain_classification",
                evidence_location="",
                evidence_snippet="",
                edge_weight=_EDGE_TYPE_WEIGHTS["domain"],
            ))

            # Hub → Symbol (incoming edge for reverse propagation)
            graph.add_edge(CausalEdge(
                from_symbol=hub_name,
                to_symbol=symbol,
                edge_type="domain",
                confidence=0.5,
                evidence=f"{hub_name} contains {symbol}",
                file_path="",
                evidence_type="domain_classification",
                evidence_location="",
                evidence_snippet="",
                edge_weight=_EDGE_TYPE_WEIGHTS["domain"],
            ))

        # Connect related hubs together (e.g., checkout → payment → tax)
        # This creates a domain-level propagation path
        hub_connections = [
            ("DOMAIN_CHECKOUT", "DOMAIN_PAYMENT"),
            ("DOMAIN_CHECKOUT", "DOMAIN_TAX"),
            ("DOMAIN_CHECKOUT", "DOMAIN_ORDER"),
            ("DOMAIN_ORDER", "DOMAIN_PAYMENT"),
            ("DOMAIN_ORDER", "DOMAIN_INVOICE"),
            ("DOMAIN_ORDER", "DOMAIN_TAX"),
            ("DOMAIN_PAYMENT", "DOMAIN_INVOICE"),
            ("DOMAIN_PAYMENT", "DOMAIN_BILLING"),
            ("DOMAIN_TAX", "DOMAIN_INVOICE"),
            ("DOMAIN_AUTH", "DOMAIN_PAYMENT"),
            ("DOMAIN_AUTH", "DOMAIN_ORDER"),
            ("DOMAIN_FULFILLMENT", "DOMAIN_INVENTORY"),
            ("DOMAIN_FULFILLMENT", "DOMAIN_ORDER"),
            ("DOMAIN_NOTIFICATION", "DOMAIN_ORDER"),
            ("DOMAIN_NOTIFICATION", "DOMAIN_PAYMENT"),
        ]

        for hub_a, hub_b in hub_connections:
            if hub_a in hubs_needed and hub_b in hubs_needed:
                # Bidirectional hub connections
                graph.add_edge(CausalEdge(
                    from_symbol=hub_a,
                    to_symbol=hub_b,
                    edge_type="domain",
                    confidence=0.3,
                    evidence=f"{hub_a} flows to {hub_b}",
                    file_path="",
                    evidence_type="domain_flow",
                    evidence_location="",
                    evidence_snippet="",
                    edge_weight=_EDGE_TYPE_WEIGHTS["domain"],
                ))
                graph.add_edge(CausalEdge(
                    from_symbol=hub_b,
                    to_symbol=hub_a,
                    edge_type="domain",
                    confidence=0.3,
                    evidence=f"{hub_b} flows to {hub_a}",
                    file_path="",
                    evidence_type="domain_flow",
                    evidence_location="",
                    evidence_snippet="",
                    edge_weight=_EDGE_TYPE_WEIGHTS["domain"],
                ))

    # Common Python/stdlib builtins to exclude from call detection noise
    COMMON_BUILTINS: set[str] = {
        "len", "str", "int", "float", "bool", "list", "dict", "set", "tuple",
        "range", "enumerate", "zip", "map", "filter", "sorted", "reversed",
        "min", "max", "sum", "abs", "round", "type", "isinstance", "hasattr",
        "getattr", "setattr", "delattr", "print", "open", "input", "format",
        "staticmethod", "classmethod", "property", "super", "__init__", "__str__",
    }

    # Additional known third-party/stdlib calls to filter out — creates garbage edges
    KNOWN_LIBRARY_CALLS: set[str] = {
        "json", "json.loads", "json.dumps",
        "datetime", "datetime.now", "date", "timedelta",
        "os", "sys", "pathlib", "Path",
        "logging", "logger", "log",
        "re", "regex",
        "random", "math", "statistics",
        "collections", "itertools", "functools",
        "typing", "Any", "Optional", "List", "Dict", "Set", "Tuple",
        "pytest", "unittest",
        "fastapi", "APIRouter", "Depends", "Query", "Body",
        "pydantic", "BaseModel", "Field",
        "requests", "httpx",
        "sqlalchemy", "session", "select",
        "django", "HttpResponse", "JsonResponse",
    }

    def _detect_call_edges(
        self,
        graph: CausalGraph,
        symbols: list[str],
        lines: list[str],
        file_path: str,
        known_symbols: set[str],
    ) -> None:
        """
        Detect data_flow edges from function calls within changed lines.

        Only creates edges when the called symbol is DEFINED in the repository
        (i.e. it's a changed function in the PR). Imported symbols are NOT
        treated as dependencies — imported ≠ executed, imported ≠ impact.

        Also creates a reverse called_by edge for each call edge, so that
        changing a callee correctly propagates back to callers.

        Uses calibrated confidence based on call context:
        - Direct invocation: higher confidence
        - Assignment: medium confidence
        - Chained call: lower confidence (more speculative)
        """
        if not symbols:
            return

        for line_no, line in enumerate(lines, start=1):
            calls = self.CALL_PATTERN.findall(line)
            for called in calls:
                # Filter out noise: self-references, control flow, builtins, known libs
                if called in ("self", "cls", "super", "if", "for", "while", "with", "return", "raise", "import", "from", "as", "try", "except", "finally", "elif", "else"):
                    continue
                if called in self.COMMON_BUILTINS:
                    continue
                if called in self.KNOWN_LIBRARY_CALLS:
                    continue

                # CRITICAL: Only create edges to KNOWN symbols (defined in repo or imported)
                # Otherwise the graph fills with garbage from json.loads(), datetime.now(), etc.
                if called not in known_symbols:
                    continue

                # Determine call pattern and evidence type/snippet
                is_assignment = "=" in line and called in line.split("=")[0]
                is_return = line.strip().startswith("return")
                is_chained = f".{called}" in line or f"self.{called}" in line

                if is_assignment:
                    evidence_type = "assignment"
                    confidence = 0.45
                elif is_return:
                    evidence_type = "return"
                    confidence = 0.50
                elif is_chained:
                    evidence_type = "function_call"
                    confidence = 0.35
                else:
                    evidence_type = "function_call"
                    confidence = 0.30

                evidence_location = f"{file_path}:{line_no}"
                evidence_snippet = line.strip()

                for symbol in symbols:
                    if called == symbol:
                        continue  # Skip self-calls

                    # Forward edge: symbol CALLS called
                    graph.add_edge(CausalEdge(
                        from_symbol=symbol,
                        to_symbol=called,
                        edge_type="calls",
                        confidence=round(confidence, 2),
                        evidence=f"{symbol} calls {called}",
                        file_path=file_path,
                        evidence_type=evidence_type,
                        evidence_location=evidence_location,
                        evidence_snippet=evidence_snippet,
                    ))

                    # Reverse edge: called CALLED_BY symbol
                    # This ensures that when 'called' changes, propagation
                    # reaches back to 'symbol' (the impacted caller).
                    graph.add_edge(CausalEdge(
                        from_symbol=called,
                        to_symbol=symbol,
                        edge_type="called_by",
                        confidence=round(confidence * 0.9, 2),  # Slightly discounted from forward
                        evidence=f"{symbol} calls {called}",
                        file_path=file_path,
                        evidence_type=evidence_type,
                        evidence_location=evidence_location,
                        evidence_snippet=evidence_snippet,
                    ))

    def _detect_shared_state_edges(
        self,
        graph: CausalGraph,
        symbols: list[str],
        lines: list[str],
        file_path: str,
    ) -> None:
        """Detect shared_state edges via named resource nodes (Task I).

        Old model (deprecated):
            For every pair of symbols that touch the same shared-state
            pattern (cache./redis./session./...), create a direct edge.
            O(n^2) edges. Treated ANY two accessors as coupled.
            This was a false-positive factory: touching the same cache
            prefix did NOT mean two symbols actually share data.

        New model:
            Extract the resource name (e.g. `cache:user`, `redis:cart`,
            `session:token`) and register it as a typed node
            (node_type="shared_state"). Then create DIRECTIONAL edges:

                writer_symbol → resource   (edge_type="shared_state")
                resource      → reader_symbol  (edge_type="shared_state")

            Propagation now flows through the resource node:
                checkout → cache:user → discount_engine

            This collapses O(n^2) edges into O(n) and matches the actual
            coupling — only writers and readers of the SAME resource are
            related.

        Direction detection:
            - WRITE:  .set(, .put(, .add(, .save(, .update(, .delete(,
                      .pop(, .store(, .write(, session[, session.
            - READ:   .get(, .fetch(, .read(, .load(, .peek(, .retrieve(
            - Fallback for bare access: assignment-target = write,
              source-side = read.
        """
        if not symbols:
            return

        # Per-symbol access map:
        #   resource_name -> (direction, evidence_type, evidence_snippet, line_no)
        accesses: dict[str, dict[str, tuple[str, str, str, int]]] = {
            sym: {} for sym in symbols
        }

        # Resources observed on this file, regardless of whether any symbol
        # matched the line. Key = resource_name, Value = (direction, evidence,
        # snippet, line_no). Used to ensure the resource is always
        # registered as a typed node in the graph (so future diffs that
        # add a reader/writer can connect to it).
        observed: dict[str, tuple[str, str, str, int]] = {}

        # Track the current enclosing function context as we walk lines.
        # When we see `def <symbol>(...)`, we enter that symbol's scope.
        # Subsequent shared_state accesses are attributed to that symbol
        # until we see another `def` or the end of the snippet.
        # This mirrors how real diffs work: the function header is one
        # line, the body is in subsequent lines.
        current_symbol: str | None = None
        symbols_set = set(symbols)

        for line_no, line in enumerate(lines, start=1):
            lower = line.lower()
            # Update function context: a `def <name>(` line opens a new scope.
            # This is how we attribute body lines to a function whose name
            # appeared on the previous line.
            def_match = re.match(r'\s*def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(', line)
            if def_match:
                name = def_match.group(1)
                if name in symbols_set:
                    current_symbol = name
                # NOTE: we don't reset on a non-matching def — that would
                # close the previous scope in a fragile way. Sticking with
                # "first def wins" semantics, which is what real diffs look
                # like (each file has at most one changed function per
                # affected hunk in our test data).

            # Which shared-state backend does this line touch?
            backend: str | None = None
            for pattern in self.SHARED_STATE_PATTERNS:
                if pattern in lower:
                    backend = pattern
                    break
            if backend is None:
                continue

            # Extract the resource name (e.g. cache:user, redis:cart)
            # This is INDEPENDENT of which symbols appear on the line —
            # the resource is identified by its name (key/attribute/subscript).
            resource_name = self._infer_shared_state_resource(line, backend)
            if not resource_name:
                # No extractable key — skip (don't create a symbol↔symbol edge).
                # This is the key fix: the old model created noisy edges here.
                continue

            # Which symbols attribute to this line?
            # 1. Symbols whose name appears directly on the line (in-line).
            # 2. The current enclosing-function context (set by `def` lines).
            in_line = [s for s in symbols if s in line]
            line_symbols: list[str] = list(in_line)
            if current_symbol and current_symbol not in in_line:
                line_symbols.append(current_symbol)

            # Determine read vs write for this access
            direction, evidence_kind = self._classify_shared_state_access(line, lower)
            evidence_snippet = line.strip()

            # Always remember we saw this resource, so we can register it
            # even if no symbol matches the line. First write wins; if
            # we already saw a read, a later write upgrades it.
            existing_obs = observed.get(resource_name)
            new_obs = (direction, evidence_kind, evidence_snippet, line_no)
            if existing_obs is None:
                observed[resource_name] = new_obs
            elif existing_obs[0] == "read" and direction == "write":
                observed[resource_name] = new_obs

            for sym in line_symbols:
                # First write wins; if already a read and now a write, upgrade.
                existing = accesses[sym].get(resource_name)
                if existing is None:
                    accesses[sym][resource_name] = new_obs
                elif existing[0] == "read" and direction == "write":
                    accesses[sym][resource_name] = new_obs

        # Register every observed resource as a typed node (idempotent).
        # This MUST happen even when no symbol matched, so the resource
        # is part of the graph and can be connected to later.
        for resource_name, (direction, evidence_kind, snippet, line_no) in observed.items():
            resource_node = graph.nodes.get(resource_name)
            if resource_node is None:
                graph.add_node(CausalNode(
                    name=resource_name,
                    node_type="shared_state",
                    metadata={
                        "resource": resource_name,
                        "file_path": file_path,
                    },
                ))
            else:
                # Promote node type if it was registered as a plain symbol
                # by a previous detector — but never demote a typed node.
                if resource_node.node_type == "symbol":
                    resource_node.node_type = "shared_state"
                    resource_node.metadata["resource"] = resource_name

        # Emit directional edges from the per-symbol access map.
        for sym in symbols:
            for resource_name, (direction, evidence_kind, snippet, line_no) in accesses[sym].items():
                confidence = 0.6 if direction == "write" else 0.5
                evidence_location = f"{file_path}:{line_no}"
                if direction == "write":
                    graph.add_edge(CausalEdge(
                        from_symbol=sym,
                        to_symbol=resource_name,
                        edge_type="shared_state",
                        confidence=confidence,
                        evidence=f"{sym} writes to {resource_name}",
                        file_path=file_path,
                        evidence_type=evidence_kind,
                        evidence_location=evidence_location,
                        evidence_snippet=snippet,
                    ))
                else:
                    graph.add_edge(CausalEdge(
                        from_symbol=resource_name,
                        to_symbol=sym,
                        edge_type="shared_state",
                        confidence=confidence,
                        evidence=f"{sym} reads from {resource_name}",
                        file_path=file_path,
                        evidence_type=evidence_kind,
                        evidence_location=evidence_location,
                        evidence_snippet=snippet,
                    ))

    def _infer_shared_state_resource(self, line: str, backend: str) -> str:
        """Extract a resource name like 'cache:user' or 'redis:cart' from a line.

        Strategy (in order):
          1. Literal string key as first arg:  cache.set("user", ...)  -> "cache:user"
          2. Bracket subscript:                session["token"]        -> "session:token"
          3. Attribute access on a backend:    redis.cart                -> "redis:cart"
          4. Backend name only (no key)        -> "cache:unknown" (still a node)
        """
        # Strip a trailing "." or "(" or "[" from the backend so it becomes
        # the bare name (e.g. "cache." -> "cache", "session[" -> "session").
        # The colon is added back when we format the resource identifier.
        bare = backend.rstrip(".([")
        prefix = f"{bare}:"

        # 1. <backend>.<method>("<key>", ...)   cache.set("user", x)
        m = re.search(
            rf'{re.escape(bare)}\s*[\.\w]*\s*\(\s*[\'"]([^\'"]+)[\'"]',
            line,
        )
        if m:
            return f"{prefix}{m.group(1)}"

        # 2. <backend>["<key>"] or session["token"]
        m = re.search(
            rf'{re.escape(bare)}\s*\[\s*[\'"]([^\'"]+)[\'"]\s*\]',
            line,
        )
        if m:
            return f"{prefix}{m.group(1)}"

        # 3. <backend>.<attr>  e.g.  redis.cart  or  session.token
        m = re.search(
            rf'{re.escape(bare)}\s*\.\s*([a-zA-Z_][a-zA-Z0-9_]*)',
            line,
        )
        if m:
            attr = m.group(1)
            # Skip method-style attribute names — they don't identify a resource
            if attr not in {"get", "set", "put", "delete", "pop", "add",
                            "update", "fetch", "read", "load", "save",
                            "store", "write", "peek", "retrieve"}:
                return f"{prefix}{attr}"

        # 4. Fallback: use the backend name as a generic resource bucket.
        #    Still a valid typed node — just less specific.
        return f"{prefix}unknown"

    def _classify_shared_state_access(
        self, line: str, lower: str,
    ) -> tuple[str, str]:
        """Classify a shared-state access as 'write' or 'read'.

        Returns (direction, evidence_type).
        """
        # Explicit write call forms: cache.set(...), session.put(...)
        for pattern in self.SHARED_STATE_WRITE_PATTERNS:
            if pattern in lower:
                # Some patterns are also read in some libs (e.g. .save() is
                # usually a write; .update() is a write). Trust the explicit set.
                return ("write", "shared_access")

        for pattern in self.SHARED_STATE_READ_PATTERNS:
            if pattern in lower:
                return ("read", "shared_access")

        # Subscript form: session["x"] = v  -> write
        if "=" in line and "[" in line and "]" in line:
            eq_idx = line.find("=")
            # If the [ is before the =, this is a subscript assignment -> write
            if line.find("[") < eq_idx:
                return ("write", "shared_access")
            return ("read", "shared_access")

        # Generic fallback: assignment to backend-prefixed name = write
        if "=" in line and any(p in line for p in self.SHARED_STATE_PATTERNS):
            return ("write", "shared_access")

        return ("read", "shared_access")

    def _detect_async_edges(
        self,
        graph: CausalGraph,
        symbols: list[str],
        lines: list[str],
        file_path: str,
    ) -> None:
        """
        Detect async_event edges from pub/sub, webhook, queue patterns.

        Production (emit) direction:
          symbol → event_name   (the symbol emits/publishes an event)

        Consumer (subscribe/handle) direction:
          event_name → symbol   (the symbol consumes/handles the event)

        This unlocks service A → queue → service B propagation — critical
        for microservices failure analysis.
        """
        for line_no, line in enumerate(lines, start=1):
            # --- Producer side: symbol emits an event ---
            for pattern in self.ASYNC_PATTERNS:
                if pattern in line.lower():
                    for symbol in symbols:
                        if symbol in line:
                            # Try to extract the event/queue name
                            event_match = re.search(rf'{re.escape(pattern)}\s*[\'"]([^\'"]+)[\'"]', line)
                            event_name = event_match.group(1) if event_match else f"event_{pattern.strip('.,(')}"

                            # Register as queue node
                            graph.add_node(CausalNode(
                                name=event_name,
                                node_type="queue",
                                metadata={"file_path": file_path},
                            ))

                            graph.add_edge(CausalEdge(
                                from_symbol=symbol,
                                to_symbol=event_name,
                                edge_type="async_event",
                                confidence=0.7,
                                evidence=f"{symbol} emits async event via {pattern}",
                                file_path=file_path,
                                evidence_type="async_emit",
                                evidence_location=f"{file_path}:{line_no}",
                                evidence_snippet=line.strip(),
                            ))

            # --- Consumer side: symbol handles/subscribes to an event ---
            for pattern in self.ASYNC_CONSUMER_PATTERNS:
                if pattern in line.lower():
                    for symbol in symbols:
                        if symbol in line:
                            # Try to extract event name from: handler(event_type), subscribe("event"), etc.
                            event_match = re.search(
                                rf'{re.escape(pattern)}\s*[\'"]([^\'"]+)[\'"]',
                                line,
                            )
                            # Also try: def handle_order_created -> extract "order_created"
                            if not event_match:
                                event_match = re.search(
                                    rf'{re.escape(pattern).replace("(", "")}\s*([a-zA-Z_][a-zA-Z0-9_]*)',
                                    line,
                                )
                            # Fallback: derive from function name if symbol name contains the event
                            event_name = ""
                            if event_match:
                                event_name = event_match.group(1)
                            else:
                                # Try to derive event name from the pattern + symbol context
                                # E.g., symbol="handle_order_created" -> event="order_created"
                                for known_event in list(graph.nodes.keys()):
                                    node = graph.nodes[known_event]
                                    if node.node_type == "queue" and known_event.lower() in line.lower():
                                        event_name = known_event
                                        break
                                if not event_name:
                                    # Derive from consumer pattern name
                                    event_name = f"event_{pattern.replace('(', '').replace(')', '')}"

                            # Register as queue node if new
                            graph.add_node(CausalNode(
                                name=event_name,
                                node_type="queue",
                                metadata={"file_path": file_path},
                            ))

                            # Consumer edge: event → symbol (event changes affect the consumer)
                            graph.add_edge(CausalEdge(
                                from_symbol=event_name,
                                to_symbol=symbol,
                                edge_type="async_event",
                                confidence=0.6,  # Slightly lower — consumer detection is more speculative
                                evidence=f"{symbol} consumes async event '{event_name}' via {pattern}",
                                file_path=file_path,
                                evidence_type="async_emit",
                                evidence_location=f"{file_path}:{line_no}",
                                evidence_snippet=line.strip(),
                            ))

    def _detect_db_edges(
        self,
        graph: CausalGraph,
        symbols: list[str],
        lines: list[str],
        file_path: str,
    ) -> None:
        """
        Detect db_dependency edges from database access patterns.

        Direction-aware propagation:
        - WRITE operations (save, update, insert, delete, commit):
          symbol → collection  (the writer affects the collection)
        - READ operations (query, filter, db. access):
          collection → symbol  (changes to the collection affect the reader)

        This unlocks the write path → storage → read path failure mode.
        """
        for line_no, line in enumerate(lines, start=1):
            for symbol in symbols:
                if symbol not in line:
                    continue

                # Check for DB write patterns: symbol → collection
                for pattern in self.DB_WRITE_PATTERNS:
                    if pattern in line.lower():
                        collection = self._infer_collection(line, pattern)
                        if collection:
                            graph.add_node(CausalNode(
                                name=collection,
                                node_type="database",
                                metadata={"collection": collection, "file_path": file_path},
                            ))
                            graph.add_edge(CausalEdge(
                                from_symbol=symbol,
                                to_symbol=collection,
                                edge_type="db_dependency",
                                confidence=0.65,
                                evidence=f"{symbol} writes to DB collection '{collection}'",
                                file_path=file_path,
                                evidence_type="db_operation",
                                evidence_location=f"{file_path}:{line_no}",
                                evidence_snippet=line.strip(),
                            ))
                        break

                # Check for DB read patterns: collection → symbol
                for pattern in self.DB_READ_PATTERNS:
                    if pattern in line.lower():
                        collection = self._infer_collection(line, pattern)
                        if collection:
                            graph.add_node(CausalNode(
                                name=collection,
                                node_type="database",
                                metadata={"collection": collection, "file_path": file_path},
                            ))
                            graph.add_edge(CausalEdge(
                                from_symbol=collection,
                                to_symbol=symbol,
                                edge_type="db_dependency",
                                confidence=0.55,  # Slightly lower for reads — less direct coupling
                                evidence=f"{symbol} reads from DB collection '{collection}'",
                                file_path=file_path,
                                evidence_type="db_operation",
                                evidence_location=f"{file_path}:{line_no}",
                                evidence_snippet=line.strip(),
                            ))
                        break

    def _infer_collection(self, line: str, pattern: str) -> str:
        """Try to infer the DB collection/table from an ORM pattern."""
        # Match patterns like: Order.save(), Checkout.objects.filter(...)
        orm_match = re.search(r'([A-Z][a-zA-Z0-9]+)\.(?:save|update|delete|objects|filter|get_or_create)', line)
        if orm_match:
            return orm_match.group(1)
        # Match patterns like: db.orders, database["checkouts"]
        db_match = re.search(r'(?:db|database)\s*[.\[]\s*[\'"]?([a-zA-Z_][a-zA-Z0-9_]*)', line)
        if db_match:
            return db_match.group(1)
        return ""

    def _detect_transaction_edges(
        self,
        graph: CausalGraph,
        symbols: list[str],
        lines: list[str],
        file_path: str,
    ) -> None:
        """
        Detect transaction_boundary edges.

        When two symbols operate within the same DB transaction/atomic block,
        a failure in one causes rollback of the other.
        This is a critical edge type for blast radius — operations in the same
        transaction have different failure semantics than operations in separate transactions.
        """
        if not symbols or len(symbols) < 2:
            return

        # Track which symbols appear near transaction boundaries
        in_transaction = False
        transaction_symbols: set[str] = set()

        for line in lines:
            # Detect transaction start
            for txn_pattern in self.TRANSACTION_PATTERNS:
                if txn_pattern in line.lower():
                    if in_transaction and len(transaction_symbols) >= 2:
                        # Close previous transaction and create edges
                        self._add_transaction_edges(graph, transaction_symbols, file_path)
                    in_transaction = True
                    transaction_symbols = set()
                    break

            # Track symbols appearing inside a transaction block
            if in_transaction:
                for symbol in symbols:
                    if symbol in line:
                        transaction_symbols.add(symbol)

            # Detect transaction end (commit, exit, or dedent)
            # NOTE: bare ")" matches every closing paren — only match explicit markers
            if in_transaction and self._is_transaction_end(line):
                if len(transaction_symbols) >= 2:
                    self._add_transaction_edges(graph, transaction_symbols, file_path)
                in_transaction = False
                transaction_symbols = set()

        # Flush remaining transaction
        if in_transaction and len(transaction_symbols) >= 2:
            self._add_transaction_edges(graph, transaction_symbols, file_path)

    def _is_transaction_end(self, line: str) -> bool:
        """Check if a line signals the end of a transaction.

        Explicit markers only — bare ')' is NOT a transaction end.
        """
        lower = line.lower()
        return any(
            marker in lower
            for marker in (
                ".commit(", "commit()", "COMMIT",
                ".rollback(", "rollback()", "ROLLBACK",
                ".close()", "close()",
                # Explicit transaction end markers
                "end transaction", "END TRANSACTION",
                # Dedent signal via line structure
                "pass", "return", "raise",
                # Explicit context manager exit
                "exit__", "__aexit__",
            )
        )

    def _add_transaction_edges(
        self,
        graph: CausalGraph,
        transaction_symbols: set[str],
        file_path: str,
    ) -> None:
        """Add transaction_boundary edges between symbols in the same transaction."""
        sym_list = list(transaction_symbols)
        for i in range(len(sym_list)):
            for j in range(i + 1, len(sym_list)):
                graph.add_edge(CausalEdge(
                    from_symbol=sym_list[i],
                    to_symbol=sym_list[j],
                    edge_type="transaction_boundary",
                    confidence=0.75,  # Higher confidence — transaction boundaries are explicit
                    evidence=f"{sym_list[i]} and {sym_list[j]} in same DB transaction",
                    file_path=file_path,
                    evidence_type="transaction_boundary",
                    evidence_location=file_path,
                    evidence_snippet=f"atomic block containing {', '.join(sym_list)}",
                ))

    def _collect_lines(self, hunks: list[Any]) -> list[str]:
        """Collect all changed line contents from hunks."""
        lines: list[str] = []
        for hunk in hunks:
            hunk_data = self._as_dict(hunk)
            for raw_line in hunk_data.get("lines", []) or []:
                line_data = self._as_dict(raw_line)
                content = str(line_data.get("content", "")).strip()
                if content and not content.startswith("#"):
                    lines.append(content)
        return lines

    def _as_dict(self, value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        if hasattr(value, "model_dump"):
            return value.model_dump()
        return {}

    # -------------------------------------------------------------------------
    # Evidence Graph — signal extraction helpers (Phase 1)
    # -------------------------------------------------------------------------

    def _extract_imports(self, full_content: str) -> list[str]:
        """Extract import module names from full file content via AST.

        Returns a flat list of module names:
          import os  →  ["os"]
          from stripe import charge  →  ["stripe"]
          from services.tax import calculate  →  ["services.tax"]
        """
        if not full_content or not isinstance(full_content, str):
            return []
        try:
            tree = ast.parse(full_content)
        except SyntaxError:
            return []

        imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append(node.module)
        return imports

    def _extract_call_targets(self, lines: list[str]) -> list[str]:
        """Extract function call targets from code lines via regex.

        Returns deduplicated list of called function names.
        Filters control flow keywords and builtins.
        """
        noise = {
            "self", "cls", "super", "if", "for", "while", "with",
            "return", "raise", "import", "from", "as", "try",
            "except", "finally", "elif", "else", "pass", "print",
            "len", "str", "int", "float", "bool", "list", "dict",
            "set", "tuple", "range", "enumerate", "zip", "map",
            "filter", "sorted", "min", "max", "sum", "type",
            "isinstance", "hasattr", "getattr", "setattr",
        }
        targets: list[str] = []
        seen: set[str] = set()
        for line in lines:
            for match in self.CALL_PATTERN.finditer(line):
                name = match.group(1)
                if name not in noise and name not in seen:
                    seen.add(name)
                    targets.append(name)
        return targets

    def _is_entrypoint(self, symbol: str, file_data: dict, repo_index: "RepositorySymbolIndex | None") -> bool:
        """Check if symbol is an HTTP entrypoint via AST decorators or repo index."""
        # Check enriched file endpoints
        for ep in file_data.get("endpoints", []) or []:
            if isinstance(ep, dict) and ep.get("function") == symbol:
                return True
        # Check repo-wide index
        if repo_index is not None and repo_index.get_endpoints_for_symbol(symbol):
            return True
        # Check full file content for route decorators
        full_content = file_data.get("full_content", "")
        if full_content:
            try:
                tree = ast.parse(full_content)
            except (SyntaxError, TypeError):
                return False
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                if node.name != symbol:
                    continue
                for dec in node.decorator_list:
                    if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute):
                        if dec.func.attr.lower() in _HTTP_METHODS or dec.func.attr == "route":
                            return True
        return False

    def _is_io(self, lines: list[str]) -> bool:
        """Check if symbol performs I/O operations via grep-based heuristics."""
        io_patterns = (
            "requests.", "httpx.", "urllib.", "aiohttp.",
            "open(", "urlopen(",
            "socket.", "connect(",
            "subprocess.", "Popen(",
        )
        for line in lines:
            lower = line.lower()
            if any(p in lower for p in io_patterns):
                return True
        return False

    def _detect_reads_state(self, lines: list[str]) -> list[str]:
        """Detect shared state resources that the symbol reads from."""
        reads: list[str] = []
        seen: set[str] = set()
        for line in lines:
            lower = line.lower()
            is_read = any(p in lower for p in self.SHARED_STATE_READ_PATTERNS)
            if not is_read:
                # Check for bare subscription reads
                if "[" in line and "]" in line and "=" in line:
                    eq_idx = line.find("=")
                    if line.find("[") > eq_idx:
                        is_read = True
            if is_read:
                for pattern in self.SHARED_STATE_PATTERNS:
                    if pattern in lower:
                        resource = self._infer_shared_state_resource(line, pattern)
                        if resource and resource not in seen:
                            seen.add(resource)
                            reads.append(resource)
                        break
        return reads

    def _detect_writes_state(self, lines: list[str]) -> bool:
        """Check if the symbol writes to any shared state resource."""
        for line in lines:
            lower = line.lower()
            if any(p in lower for p in self.SHARED_STATE_WRITE_PATTERNS):
                return True
            # Check for subscription writes
            if "[" in line and "]" in line and "=" in line:
                eq_idx = line.find("=")
                if line.find("[") < eq_idx:
                    return True
        return False

    def build_evidence_graph(
        self,
        enriched_files: list[dict],
        repo_index: "RepositorySymbolIndex | None" = None,
    ) -> list[dict]:
        """Build the evidence graph: enriched symbol nodes with behavioral signals.

        For every changed symbol across all enriched files, extracts:
          - is_entrypoint: has HTTP route decorators (FastAPI/Flask)
          - is_io: performs network/file I/O
          - writes_state: mutates shared state (cache/redis/session)
          - reads_state: reads shared state resources
          - calls: function call targets in the changed lines
          - called_by: reverse callers (from causal graph edges)
          - imports: module imports from the file

        Args:
            enriched_files: Same enriched_files passed to build().
            repo_index: Optional repo-wide symbol index for endpoint lookup.

        Returns:
            List of EvidenceNode dicts (see EvidenceNode.to_dict).
        """
        if not enriched_files:
            return []

        ri = repo_index if repo_index is not None else getattr(self, "_repo_index", None)
        known_symbols = self._repo_symbols | (ri.known_symbols if ri else set())

        evidence_nodes: list[dict] = []

        for file_data in enriched_files:
            file_path = str(file_data.get("file_path", ""))
            hunks = file_data.get("hunks", []) or []
            hunk_lines = self._collect_lines(hunks)
            full_content = file_data.get("full_content", "")

            # AST-based imports from full file content
            file_imports = self._extract_imports(full_content)

            for fn in (file_data.get("changed_functions", []) or []):
                fn_data = self._as_dict(fn)
                name = str(fn_data.get("name", "")).strip()
                if not name:
                    continue

                symbol = name.split(".")[-1] if "." in name else name
                change_type = str(fn_data.get("change_type", "modified"))
                node = EvidenceNode(
                    symbol=symbol,
                    file=file_path,
                    change_type=change_type,
                )

                # --- Signal: entrypoint ---
                node.signals.is_entrypoint = self._is_entrypoint(symbol, file_data, ri)

                # --- Signal: I/O ---
                node.signals.is_io = self._is_io(hunk_lines)

                # --- Signal: writes/reads state ---
                node.signals.writes_state = self._detect_writes_state(hunk_lines)
                node.signals.reads_state = self._detect_reads_state(hunk_lines)

                # --- Signal: calls (regex from hunk lines) ---
                node.signals.calls = self._extract_call_targets(hunk_lines)

                # --- Signal: called_by (from causal graph incoming edges) ---
                if hasattr(self, "_graph") and self._graph is not None:
                    incoming = self._graph.get_incoming(symbol)
                    caller_set: set[str] = set()
                    for edge in incoming:
                        if edge.edge_type in ("calls", "called_by"):
                            caller_set.add(edge.from_symbol)
                    node.signals.called_by = sorted(caller_set)

                # --- Signal: imports ---
                node.signals.imports = file_imports

                evidence_nodes.append(node.to_dict())

        # Pass 2: backfill called_by from cross-file causal edges.
        # Build a quick index from this evidence graph.
        evidence_symbols = {n["symbol"] for n in evidence_nodes}
        evidence_index: dict[str, dict] = {
            n["symbol"]: n for n in evidence_nodes
        }

        for node_dict in evidence_nodes:
            sym = node_dict["symbol"]
            called = node_dict["signals"]["calls"]
            for target in called:
                if target in evidence_index:
                    target_signals = evidence_index[target]["signals"]
                    if sym not in target_signals["called_by"]:
                        target_signals["called_by"].append(sym)
                        target_signals["called_by"].sort()

        # Rebuild causal graph for edge-based called_by backfill
        if not hasattr(self, "_graph") or self._graph is None:
            self._graph = self.build(enriched_files, repo_index=ri)

        for node_dict in evidence_nodes:
            sym = node_dict["symbol"]
            incoming = self._graph.get_incoming(sym)
            for edge in incoming:
                if edge.edge_type in ("calls", "called_by"):
                    caller = edge.from_symbol
                    if caller in evidence_index:
                        target_signals = evidence_index[caller]["signals"]
                        if sym not in target_signals["calls"]:
                            # caller called sym, so caller.calls should include sym
                            if sym not in target_signals["calls"]:
                                target_signals["calls"].append(sym)
                                target_signals["calls"].sort()

        return evidence_nodes


    # -------------------------------------------------------------------------
    # Phase 2 — Weak Causal Edges
    # -------------------------------------------------------------------------

    _WEAK_NOISE: set[str] = {
        "self", "cls", "super", "if", "for", "while", "with",
        "return", "raise", "import", "from", "as", "try",
        "except", "finally", "elif", "else", "pass", "print",
        "len", "str", "int", "float", "bool", "list", "dict",
        "set", "tuple", "range", "enumerate", "zip", "map",
        "filter", "sorted", "min", "max", "sum", "type",
        "isinstance", "hasattr", "getattr", "setattr",
        "json", "datetime", "os", "sys", "logging", "logger",
        "requests", "httpx", "fastapi", "pydantic",
    }

    def build_weak_edges(
        self,
        enriched_files: list[dict],
        repo_index: "RepositorySymbolIndex | None" = None,
    ) -> list[dict]:
        """Build weak causal edges with evidence tokens (Phase 2).

        Produces evidence edges with 5 types:
            CALLS, SHARES_STATE, DATA_FLOW, CONTROL_FLOW, CONTRACT_DEPENDENCY

        Every edge MUST have ≥1 evidence string. This replaces LLM reasoning
        with grounded, probabilistic structure.

        Returns:
            List of WeakEdge dicts (see WeakEdge.to_dict).
        """
        if not enriched_files:
            return []

        ri = repo_index if repo_index is not None else getattr(self, "_repo_index", None)
        known_symbols = self._repo_symbols | (ri.known_symbols if ri else set())

        # Ensure causal graph is built for cross-reference
        if not hasattr(self, "_graph") or self._graph is None:
            self.build(enriched_files, repo_index=ri)

        weak_edges: list[WeakEdge] = []
        seen_keys: set[tuple[str, str, str]] = set()

        def _add(edge: WeakEdge) -> None:
            """Add edge if valid and not duplicate."""
            if not edge.evidence:
                return  # REQUIREMENT: every edge must have ≥1 evidence
            key = (edge.from_symbol, edge.to_symbol, edge.edge_type)
            if key in seen_keys:
                return
            seen_keys.add(key)
            weak_edges.append(edge)

        for file_data in enriched_files:
            file_path = str(file_data.get("file_path", ""))
            hunks = file_data.get("hunks", []) or []
            hunk_lines = self._collect_lines(hunks)
            full_content = file_data.get("full_content", "")
            file_imports = self._extract_imports(full_content)

            symbols = [
                str(self._as_dict(fn).get("name", "")).split(".")[-1]
                for fn in (file_data.get("changed_functions", []) or [])
                if str(self._as_dict(fn).get("name", "")).strip()
            ]

            self._build_weak_call_edges(weak_edges, symbols, hunk_lines, file_path, known_symbols, _add)
            self._build_weak_shared_state_edges(weak_edges, symbols, hunk_lines, file_path, _add)
            self._build_weak_data_flow_edges(weak_edges, symbols, hunk_lines, file_path, known_symbols, _add)
            self._build_weak_control_flow_edges(weak_edges, symbols, hunk_lines, file_path, _add)
            self._build_weak_contract_dependency_edges(weak_edges, symbols, file_path, file_imports, known_symbols, _add)

        return [e.to_dict() for e in weak_edges]

    def _build_weak_call_edges(
        self,
        edges: list[WeakEdge],
        symbols: list[str],
        lines: list[str],
        file_path: str,
        known_symbols: set[str],
        add: Callable[["WeakEdge"], None],
    ) -> None:
        """Detect CALLS edges: direct function invocations."""
        for line_no, line in enumerate(lines, start=1):
            calls = self.CALL_PATTERN.findall(line)
            for called in calls:
                if called in self._WEAK_NOISE:
                    continue
                if called in self.COMMON_BUILTINS:
                    continue
                if called in self.KNOWN_LIBRARY_CALLS:
                    continue
                if called not in known_symbols:
                    continue

                evidence: list[str] = []
                # Primary evidence: direct invocation found
                evidence.append(f"direct invocation found in {file_path}")
                # Secondary: symbol appears in function body
                snippet = line.strip()
                if snippet:
                    evidence.append(f"function call pattern detected: `{called}()` in changed code")
                # Tertiary: call graph match
                evidence.append(f"function name `{called}` appears in call graph of changed symbols")

                is_chained = f".{called}" in line
                is_assignment = "=" in line and called in line.split("=")[0]
                if is_chained:
                    confidence = 0.72
                elif is_assignment:
                    confidence = 0.78
                else:
                    confidence = 0.85

                for symbol in symbols:
                    if called == symbol:
                        continue
                    add(WeakEdge(
                        from_symbol=symbol,
                        to_symbol=called,
                        edge_type="CALLS",
                        confidence=confidence,
                        evidence=evidence,
                        file_path=file_path,
                    ))

    def _build_weak_shared_state_edges(
        self,
        edges: list[WeakEdge],
        symbols: list[str],
        lines: list[str],
        file_path: str,
        add: Callable[["WeakEdge"], None],
    ) -> None:
        """Detect SHARES_STATE edges: shared state coupling via cache/redis/session."""
        # Track resource access per symbol
        # resource_name -> [(direction, symbol, snippet)]
        resource_access: dict[str, list[tuple[str, str, str]]] = {}

        for line in lines:
            lower = line.lower()
            backend: str | None = None
            for pattern in self.SHARED_STATE_PATTERNS:
                if pattern in lower:
                    backend = pattern
                    break
            if backend is None:
                continue

            resource = self._infer_shared_state_resource(line, backend)
            if not resource:
                continue

            is_write = any(p in lower for p in self.SHARED_STATE_WRITE_PATTERNS)
            direction = "write" if is_write else "read"

            for symbol in symbols:
                if symbol in line or (symbol.lower() in lower):
                    resource_access.setdefault(resource, []).append(
                        (direction, symbol, line.strip()),
                    )

        # Edges: for each resource, create writer→reader edges
        for resource, accesses in resource_access.items():
            writers = [(s, snip) for d, s, snip in accesses if d == "write"]
            readers = [(s, snip) for d, s, snip in accesses if d == "read"]

            for writer_sym, writer_snip in writers:
                for reader_sym, reader_snip in readers:
                    if writer_sym == reader_sym:
                        continue
                    evidence = [
                        f"symbol `{writer_sym}` writes to `{resource}` in {file_path}",
                        f"symbol `{reader_sym}` reads from `{resource}` in {file_path}",
                        f"shared state access detected via `{resource}` coupling",
                    ]
                    add(WeakEdge(
                        from_symbol=writer_sym,
                        to_symbol=reader_sym,
                        edge_type="SHARES_STATE",
                        confidence=0.65,
                        evidence=evidence,
                        file_path=file_path,
                    ))

    def _build_weak_data_flow_edges(
        self,
        edges: list[WeakEdge],
        symbols: list[str],
        lines: list[str],
        file_path: str,
        known_symbols: set[str],
        add: Callable[["WeakEdge"], None],
    ) -> None:
        """Detect DATA_FLOW edges: result of one symbol feeds another."""
        # Pattern: `x = symbol(...)` or `result = symbol().method()`
        assignment_pattern = re.compile(
            r'([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*(?:self\.)?([a-zA-Z_][a-zA-Z0-9_]*)\s*\('
        )
        for line_no, line in enumerate(lines, start=1):
            m = assignment_pattern.search(line)
            if not m:
                continue
            target_var = m.group(1)
            source_fn = m.group(2)

            if source_fn in self._WEAK_NOISE or source_fn in self.COMMON_BUILTINS:
                continue
            if source_fn not in known_symbols:
                continue

            # Find symbols that use this variable on subsequent lines
            for symbol in symbols:
                if symbol == source_fn:
                    continue
                # Check if the variable appears in lines that mention this symbol
                for later_line in lines:
                    if target_var in later_line and symbol in later_line and symbol != target_var:
                        evidence = [
                            f"result of `{source_fn}()` assigned to `{target_var}` in {file_path}",
                            f"variable `{target_var}` used by `{symbol}` in changed code",
                            "assignment chain detected in function body",
                        ]
                        add(WeakEdge(
                            from_symbol=source_fn,
                            to_symbol=symbol,
                            edge_type="DATA_FLOW",
                            confidence=0.58,
                            evidence=evidence,
                            file_path=file_path,
                        ))
                        break

    def _build_weak_control_flow_edges(
        self,
        edges: list[WeakEdge],
        symbols: list[str],
        lines: list[str],
        file_path: str,
        add: Callable[["WeakEdge"], None],
    ) -> None:
        """Detect CONTROL_FLOW edges: one symbol gates execution of another."""
        control_keywords = ("if ", "elif ", "while ", "try:", "except ", "with ")
        # Pattern: `if symbol(...):` or `with symbol(...):` etc.
        conditional_pattern = re.compile(
            r'(?:if|elif|while|with)\s+(?:self\.)?([a-zA-Z_][a-zA-Z0-9_]*)\s*\('
        )
        # Pattern: `return symbol(...)` which is conditional on prior guards
        guard_pattern = re.compile(
            r'return\s+(?:self\.)?([a-zA-Z_][a-zA-Z0-9_]*)\s*\('
        )

        for line_no, line in enumerate(lines, start=1):
            lower = line.lower().lstrip()
            gated_symbols: list[str] = []

            m = conditional_pattern.search(line)
            if m:
                gated_symbols.append(m.group(1))

            if lower.startswith("return"):
                m2 = guard_pattern.search(line)
                if m2:
                    gated_symbols.append(m2.group(1))

            for gated in gated_symbols:
                if gated in self._WEAK_NOISE or gated in self.COMMON_BUILTINS:
                    continue
                # The symbol that appears in this line as the condition
                for symbol in symbols:
                    if symbol == gated:
                        continue
                    # If the conditional symbol is called by `symbol`, there's control flow
                    if symbol in line and gated in line:
                        evidence = [
                            f"symbol `{gated}` appears in conditional context in {file_path}",
                            f"execution gated by `{symbol}` in changed code",
                            "control flow dependency detected in function body",
                        ]
                        add(WeakEdge(
                            from_symbol=symbol,
                            to_symbol=gated,
                            edge_type="CONTROL_FLOW",
                            confidence=0.48,
                            evidence=evidence,
                            file_path=file_path,
                        ))

    def _build_weak_contract_dependency_edges(
        self,
        edges: list[WeakEdge],
        symbols: list[str],
        file_path: str,
        file_imports: list[str],
        known_symbols: set[str],
        add: Callable[["WeakEdge"], None],
    ) -> None:
        """Detect CONTRACT_DEPENDENCY edges: import-based coupling."""
        for symbol in symbols:
            for module in file_imports:
                if module in self._WEAK_NOISE:
                    continue
                evidence = [
                    f"import path suggests dependency: `{module}` imported in {file_path}",
                    f"module `{module}` appears in import graph of changed file",
                ]
                # Higher confidence if the module name is a known symbol
                if module in known_symbols:
                    confidence = 0.52
                    evidence.append(f"module `{module}` is a known symbol in the repository")
                else:
                    confidence = 0.38
                    evidence.append(f"module `{module}` referenced in import section")
                add(WeakEdge(
                    from_symbol=symbol,
                    to_symbol=module,
                    edge_type="CONTRACT_DEPENDENCY",
                    confidence=confidence,
                    evidence=evidence,
                    file_path=file_path,
                ))


def build_causal_graph(
    enriched_files: list[dict],
    behavior_diffs: list[Any] | None = None,
    repo_index: RepositorySymbolIndex | None = None,
) -> CausalGraph:
    """Convenience function for building the causal graph.

    Forwards `repo_index` to CausalGraphBuilder.build() so callers (i.e. the
    orchestrator in FULL_FILE mode) can opt into repo-wide symbol expansion
    without touching the builder directly.
    """
    return CausalGraphBuilder().build(
        enriched_files,
        behavior_diffs,
        repo_index=repo_index,
    )


def build_evidence_graph(
    enriched_files: list[dict],
    repo_index: RepositorySymbolIndex | None = None,
) -> list[dict]:
    """Convenience function for building the evidence graph.

    Builds the causal graph first (to populate called_by edges), then
    extracts per-symbol behavioral signals. Returns a list of
    EvidenceNode dicts (see EvidenceNode.to_dict).
    """
    builder = CausalGraphBuilder()
    builder.build(enriched_files, repo_index=repo_index)
    return builder.build_evidence_graph(enriched_files, repo_index=repo_index)


def build_weak_edges(
    enriched_files: list[dict],
    repo_index: RepositorySymbolIndex | None = None,
) -> list[dict]:
    """Convenience function for building weak causal edges.

    Builds the causal graph first, then produces weak edges with 5 types
    (CALLS, SHARES_STATE, DATA_FLOW, CONTROL_FLOW, CONTRACT_DEPENDENCY).
    Each edge has ≥1 evidence string. Returns list of WeakEdge dicts.
    """
    builder = CausalGraphBuilder()
    builder.build(enriched_files, repo_index=repo_index)
    return builder.build_weak_edges(enriched_files, repo_index=repo_index)

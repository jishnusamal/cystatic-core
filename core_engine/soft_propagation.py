"""
Layer 2 — Soft Propagation Graph (Probabilistic Structure)

Bridges the gap between change signals (Layer 1) and execution paths (Layer 3).

These are NOT truth, NOT hallucination, NOT execution guarantees.
They are "likely propagation structure" — weak signals the LLM can use
to reason even when execution paths are sparse.

Rules (deterministic):
  RULE 1 — DOMAIN FLOW (strongest): hardcoded pipeline
    checkout → order → invoice → tax → payment → ledger
  RULE 2 — SYMBOL TOKEN MATCH: shared tokens connect symbols
  RULE 3 — CHANGE CO-LOCATION: multiple modified symbols in same file → weakly connect
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ══════════════════════════════════════════════════════════════════════════════
# Data Structures
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class SoftEdge:
    """A soft propagation edge between two symbols."""
    from_symbol: str
    to_symbol: str
    edge_type: str = "semantic_propagation"
    confidence: float = 0.2  # 0.2–0.6 range
    source: str = "domain_flow"  # domain_flow | naming | shared_service
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "from": self.from_symbol,
            "to": self.to_symbol,
            "edge_type": self.edge_type,
            "confidence": round(self.confidence, 3),
            "source": self.source,
            "reason": self.reason,
        }


# ══════════════════════════════════════════════════════════════════════════════
# Domain Pipeline (RULE 1)
# ══════════════════════════════════════════════════════════════════════════════

# The canonical billing pipeline
DOMAIN_PIPELINE: list[str] = [
    "checkout", "order", "invoice", "tax", "payment", "ledger",
]

# Extended: domain → likely downstream domains
DOMAIN_FLOW_MAP: dict[str, list[str]] = {
    "checkout": ["order", "cart", "payment", "tax"],
    "cart": ["checkout", "order"],
    "order": ["invoice", "fulfillment", "payment"],
    "invoice": ["payment", "billing"],
    "tax": ["invoice", "payment"],
    "payment": ["invoice", "ledger", "fulfillment", "notification"],
    "ledger": ["notification", "billing"],
    "auth": ["user", "session", "profile"],
    "user": ["auth", "profile", "notification"],
    "login": ["auth", "session", "user"],
    "session": ["auth", "user"],
    "fulfillment": ["notification", "shipping"],
    "shipping": ["fulfillment", "notification"],
    "notification": [],
    "email": ["notification"],
    "sms": ["notification"],
    "webhook": ["notification", "billing"],
    "discount": ["cart", "checkout", "payment"],
    "coupon": ["discount", "cart", "checkout"],
    "subscription": ["billing", "invoice", "payment"],
    "billing": ["invoice", "payment", "notification"],
    "catalog": ["cart", "checkout"],
    "inventory": ["fulfillment", "catalog"],
    "pricing": ["cart", "checkout", "invoice"],
    "cache": [],
    "redis": ["cache"],
    "general": [],
}


# ══════════════════════════════════════════════════════════════════════════════
# Soft Propagation Generator
# ══════════════════════════════════════════════════════════════════════════════

def _extract_tokens(symbol: str) -> set[str]:
    """Extract meaningful tokens from a symbol name."""
    symbol_lower = symbol.lower()
    # Split on underscore, camelCase, and digits
    parts = set()
    for part in symbol_lower.split("_"):
        if part and part not in {"self", "cls", "get", "set", "handle", "process", "_", ""}:
            parts.add(part)
    return parts


def _domain_flow_edges(
    symbols: dict[str, str],
) -> list[SoftEdge]:
    """RULE 1 — Domain flow edges.

    For each symbol, if its name contains a domain key that maps to
    downstream domains, create weak edges to symbols in those downstream domains.
    """
    edges: list[SoftEdge] = []
    symbol_domains: dict[str, str] = {}

    for sym in symbols:
        sym_lower = sym.lower()
        matched_domain = "general"
        for domain in DOMAIN_FLOW_MAP:
            if domain in sym_lower:
                matched_domain = domain
                break
        symbol_domains[sym] = matched_domain

    sym_list = list(symbols.keys())
    for i, from_sym in enumerate(sym_list):
        from_domain = symbol_domains[from_sym]
        downstream_keys = DOMAIN_FLOW_MAP.get(from_domain, [])

        for to_sym in sym_list:
            if from_sym == to_sym:
                continue
            to_domain = symbol_domains[to_sym]

            # Check if to_domain is a valid downstream of from_domain
            if to_domain in downstream_keys or _is_near_match(to_domain, downstream_keys):
                edges.append(SoftEdge(
                    from_symbol=from_sym,
                    to_symbol=to_sym,
                    source="domain_flow",
                    confidence=0.4,
                    reason=f"{from_domain} → {to_domain} is canonical billing flow",
                ))

    return edges


def _is_near_match(domain: str, downstream_keys: list[str]) -> bool:
    """Check if domain is a near-match of any downstream key."""
    domain_lower = domain.lower()
    for key in downstream_keys:
        key_lower = key.lower()
        if key_lower in domain_lower or domain_lower in key_lower:
            return True
    return False


def _symbol_token_edges(
    symbols: dict[str, str],
) -> list[SoftEdge]:
    """RULE 2 — Symbol token match edges.

    If two symbols share a meaningful token (tax, invoice, order, payment, etc.),
    create a weak connection.
    """
    edges: list[SoftEdge] = []
    high_value_tokens = {
        "tax", "invoice", "order", "payment", "checkout", "charge",
        "auth", "user", "session", "cache", "billing", "subscription",
        "refund", "payout", "price", "cost", "total", "amount",
        "cart", "discount", "coupon", "shipping", "fulfillment",
        "notification", "email", "webhook", "catalog", "inventory",
    }

    sym_tokens: dict[str, set[str]] = {}
    for sym in symbols:
        tokens = _extract_tokens(sym)
        # Only keep high-value tokens
        tokens = {t for t in tokens if t in high_value_tokens}
        sym_tokens[sym] = tokens

    sym_list = list(symbols.keys())
    for i, from_sym in enumerate(sym_list):
        from_tokens = sym_tokens[from_sym]
        if not from_tokens:
            continue

        for to_sym in sym_list[i + 1:]:
            to_tokens = sym_tokens[to_sym]
            if not to_tokens:
                continue

            shared = from_tokens & to_tokens
            if shared:
                edges.append(SoftEdge(
                    from_symbol=from_sym,
                    to_symbol=to_sym,
                    source="naming",
                    confidence=0.25,
                    reason=f"shared token(s): {', '.join(sorted(shared))}",
                ))

    return edges


def _co_location_edges(
    symbols: dict[str, str],
) -> list[SoftEdge]:
    """RULE 3 — Change co-location edges.

    If multiple modified symbols are in the same file, fully connect them weakly.
    """
    edges: list[SoftEdge] = []

    # Group symbols by file
    file_groups: dict[str, list[str]] = {}
    for sym, file_path in symbols.items():
        if file_path:
            file_groups.setdefault(file_path, []).append(sym)

    for file_path, group in file_groups.items():
        if len(group) < 2:
            continue

        for i, from_sym in enumerate(group):
            for to_sym in group[i + 1:]:
                # Skip if domain flow already covers this pair
                # (co-location is weaker)
                edges.append(SoftEdge(
                    from_symbol=from_sym,
                    to_symbol=to_sym,
                    source="shared_service",
                    confidence=0.15,
                    reason=f"co-located in same file: {file_path}",
                ))

    return edges


# ══════════════════════════════════════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════════════════════════════════════

def build_soft_propagation_graph(
    all_changed_symbols: list[dict[str, str]],
    existing_edges: set[tuple[str, str]] | None = None,
) -> list[SoftEdge]:
    """Build the soft propagation graph from changed symbols.

    Args:
        all_changed_symbols: List of dicts with 'symbol' and 'file' keys.
        existing_edges: Optional set of (from, to) tuples already covered by
            the causal graph. Soft edges that duplicate real edges are skipped.

    Returns:
        List of SoftEdge entries, sorted by confidence descending.
    """
    # Build symbol → file_path map
    symbols: dict[str, str] = {}
    for entry in all_changed_symbols:
        sym = entry.get("symbol", "") or entry.get("name", "")
        file_path = entry.get("file", "") or entry.get("file_path", "")
        if sym:
            bare = sym.split(".")[-1] if "." in sym else sym
            if bare not in symbols:
                symbols[bare] = file_path

    if not symbols:
        return []

    existing = existing_edges or set()

    # Collect edges from all rules
    all_edges: list[SoftEdge] = []
    dedup: dict[tuple[str, str], SoftEdge] = {}

    for edge_list in [
        _domain_flow_edges(symbols),
        _symbol_token_edges(symbols),
        _co_location_edges(symbols),
    ]:
        for edge in edge_list:
            key = (edge.from_symbol, edge.to_symbol)

            # Skip if this edge already exists in the causal graph
            if key in existing:
                continue

            # Take max confidence for same from→to pair
            if key in dedup:
                if edge.confidence > dedup[key].confidence:
                    dedup[key] = edge
            else:
                dedup[key] = edge

    all_edges = list(dedup.values())

    # Sort by confidence descending
    all_edges.sort(key=lambda e: (-e.confidence, e.source))

    return all_edges


def extract_existing_edges_from_graph(
    causal_graph: Any | None = None,
) -> set[tuple[str, str]]:
    """Extract (from, to) tuples from an existing causal graph.

    Used to prevent soft edges from duplicating real edges.
    """
    existing: set[tuple[str, str]] = set()

    if causal_graph is None:
        return existing

    # Try to_dict() edges
    if hasattr(causal_graph, "edges"):
        for edge in causal_graph.edges:
            if hasattr(edge, "from_symbol") and hasattr(edge, "to_symbol"):
                existing.add((edge.from_symbol, edge.to_symbol))
    elif hasattr(causal_graph, "to_dict"):
        graph_dict = causal_graph.to_dict()
        for edge in graph_dict.get("edges", []):
            from_sym = edge.get("from", "") or edge.get("from_symbol", "")
            to_sym = edge.get("to", "") or edge.get("to_symbol", "")
            if from_sym and to_sym:
                existing.add((from_sym, to_sym))

    return existing
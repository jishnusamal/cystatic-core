"""
Failure Simulation Engine — Probabilistic Causal Walk Graph.

Converts anchors into a pseudo-graph and runs BFS with decay to generate
deterministic failure chains.

Mechanisms:
1. Infer edges from co-tags + file proximity + causal graph edges
2. Assign transition probabilities
3. Simulate propagation (BFS with decay)
4. Generate failure chains (3-5 step scenarios)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from collections import deque
import math

from core_engine.change_influence import _is_test_or_mock_symbol


# ── Edge weight defaults ─────────────────────────────────────────────────
_SAME_FILE_WEIGHT: float = 0.7
_SAME_FLOW_TAG_WEIGHT: float = 0.5
_SAME_DOMAIN_WEIGHT: float = 0.3
_CAUSAL_EDGE_WEIGHT: float = 0.85  # Higher confidence — causal edges are grounded
_DECAY_PER_HOP: float = 0.6
_STOP_THRESHOLD: float = 0.05

# Domain regions for grouping
_DOMAIN_REGIONS: dict[str, str] = {
    "checkout": "checkout",
    "order": "order",
    "invoice": "invoice",
    "payment": "payment",
    "tax": "tax",
    "billing": "billing",
    "billing_core": "billing",
    "billing_output": "billing",
    "billing_calculation": "billing",
    "billing_pricing": "billing",
    "billing_cart": "billing",
    "billing_recurring": "billing",
    "money_movement": "payment",
    "fulfillment": "fulfillment",
    "inventory": "inventory",
    "catalog": "catalog",
    "identity": "auth",
    "auth": "auth",
    "subscription": "billing",
    "notification": "notification",
    "cache": "cache",
    "general": "general",
}

# When no edges exist at all, force-build edges from shared flow tags.
# These are the tags that indicate a meaningful system flow.
_FLOW_TRIGGER_TAGS: set[str] = {
    "order", "payment", "tax", "invoice", "checkout", "billing",
    "charge", "refund", "subscription", "auth", "notification",
    "fulfillment", "inventory", "catalog", "shipping",
}

# Mapping from causal edge types to transition probability adjustments
_CAUSAL_TYPE_PROB_MAP: dict[str, float] = {
    "calls": 0.85,
    "called_by": 0.75,
    "data_flow": 0.7,
    "control_flow": 0.65,
    "shared_state": 0.7,
    "async_event": 0.6,
    "db_dependency": 0.65,
    "transaction_boundary": 0.8,
}


@dataclass
class InferredEdge:
    """An inferred edge between two symbols in the pseudo-graph."""
    from_symbol: str
    to_symbol: str
    tag_overlap_score: float = 0.0
    file_proximity_score: float = 0.0
    domain_similarity: float = 0.0
    transition_probability: float = 0.0
    edge_type: str = "inferred"  # "same_file" | "same_flow_tag" | "same_domain" | "causal"

    def to_dict(self) -> dict[str, Any]:
        return {
            "from": self.from_symbol,
            "to": self.to_symbol,
            "tag_overlap_score": round(self.tag_overlap_score, 3),
            "file_proximity_score": round(self.file_proximity_score, 3),
            "domain_similarity": round(self.domain_similarity, 3),
            "transition_probability": round(self.transition_probability, 3),
            "edge_type": self.edge_type,
        }


@dataclass
class FailureChain:
    """A single failure propagation chain."""
    path: list[str]
    probabilities: list[float]
    total_probability: float
    steps: int
    description: str = ""
    failure_class: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "probabilities": [round(p, 4) for p in self.probabilities],
            "total_probability": round(self.total_probability, 4),
            "steps": self.steps,
            "description": self.description,
            "failure_class": self.failure_class,
        }


@dataclass
class SymbolNode:
    """A symbol in the pseudo-graph with its metadata."""
    symbol: str
    file_path: str = ""
    tags: set[str] = field(default_factory=set)
    domain: str = "general"
    domain_region: str = "general"
    node_type: str = "runtime"  # "runtime" | "test"

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "file_path": self.file_path,
            "tags": sorted(self.tags),
            "domain": self.domain,
            "domain_region": self.domain_region,
            "node_type": self.node_type,
        }


# ═══════════════════════════════════════════════════════════════════════════
# Step 1: Infer edges
# ═══════════════════════════════════════════════════════════════════════════

def _jaccard_similarity(set_a: set[str], set_b: set[str]) -> float:
    """Jaccard similarity between two sets."""
    if not set_a and not set_b:
        return 1.0
    if not set_a or not set_b:
        return 0.0
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union)


def _compute_tag_overlap(a_tags: set[str], b_tags: set[str]) -> float:
    """Compute tag overlap score (0.0–1.0)."""
    return _jaccard_similarity(a_tags, b_tags)


def _compute_file_proximity(a_path: str, b_path: str) -> float:
    """Compute file proximity score (0.0–1.0) using weighted locality.

    Semantic replacement for naive directory prefix matching:
    - Same class (inferred from filename matching class patterns) → 0.9
    - Same module (same file) → 0.7
    - Same package (common parent directory) → 0.5
    - Import relationship (detected via tags) → 0.6
    - No meaningful locality → 0.0

    The old "same directory → 0.6" heuristic is REMOVED — it created
    edges between unrelated files that happened to share a parent directory.
    """
    if not a_path or not b_path:
        return 0.0
    if a_path == b_path:
        return 0.7  # Same module (file)

    a_parts = a_path.replace("\\", "/").split("/")
    b_parts = b_path.replace("\\", "/").split("/")

    # Same class: files with matching class-like names (e.g., OrderService.py)
    # This is a heuristic — we look for CamelCase filenames that match
    a_file = a_parts[-1] if a_parts else ""
    b_file = b_parts[-1] if b_parts else ""
    # Extract potential class names (CamelCase without extension)
    a_class = a_file.split(".")[0] if "." in a_file else a_file
    b_class = b_file.split(".")[0] if "." in b_file else b_file
    if a_class and b_class and a_class == b_class and a_class[0].isupper():
        return 0.9  # Same class

    # Same package: common parent directory (excluding filename)
    # e.g., server/polar/order/service.py and server/polar/order/models.py
    if len(a_parts) >= 2 and len(b_parts) >= 2:
        a_pkg = a_parts[:-1]  # All but filename
        b_pkg = b_parts[:-1]
        common_pkg = 0
        for a, b in zip(a_pkg, b_pkg):
            if a == b:
                common_pkg += 1
            else:
                break
        if common_pkg >= 1:
            return 0.5  # Same package

    # Note: "same directory" (common prefix >= 2 with old logic) is REMOVED
    # It was connecting unrelated files like server/payment/x.py and server/order/y.py
    # just because they shared "server/" prefix.

    return 0.0


def _compute_domain_similarity(a_domain: str, b_domain: str) -> float:
    """Compute domain similarity (0.0–1.0).

    Same domain → 1.0
    Same domain region → 0.5
    Different → 0.0
    """
    if a_domain == b_domain:
        return 1.0

    a_region = _DOMAIN_REGIONS.get(a_domain, "general")
    b_region = _DOMAIN_REGIONS.get(b_domain, "general")
    if a_region == b_region:
        return 0.5
    return 0.0


# ═══════════════════════════════════════════════════════════════════════════
# Causal edge conversion
# ═══════════════════════════════════════════════════════════════════════════

def _convert_causal_edge_to_inferred(
    edge_dict: dict[str, Any],
) -> InferredEdge | None:
    """Convert a causal graph edge dict to an InferredEdge.

    Expected dict format (from CausalEdge.to_dict):
        {
            "from": "symbol_a",
            "to": "symbol_b",
            "type": "calls",
            "confidence": 0.85,
            ...
        }

    Returns None if the edge dict is malformed.
    """
    from_sym = edge_dict.get("from", "")
    to_sym = edge_dict.get("to", "")
    if not from_sym or not to_sym:
        return None

    edge_type = edge_dict.get("type", "calls")
    confidence = edge_dict.get("confidence", 0.5)

    # Map the causal edge type to a transition probability
    base_prob = _CAUSAL_TYPE_PROB_MAP.get(edge_type, 0.5)
    transition_prob = base_prob * confidence

    return InferredEdge(
        from_symbol=from_sym,
        to_symbol=to_sym,
        tag_overlap_score=0.0,
        file_proximity_score=0.0,
        domain_similarity=0.0,
        transition_probability=min(transition_prob, 1.0),
        edge_type=f"causal:{edge_type}",
    )


def _convert_causal_edges(
    causal_edges: list[dict[str, Any]],
) -> list[InferredEdge]:
    """Convert a list of causal graph edge dicts to InferredEdge objects.

    Deduplicates by (from, to) — the first edge with the highest
    transition probability wins.
    """
    converted: dict[tuple[str, str], InferredEdge] = {}
    for edge_dict in causal_edges:
        inferred = _convert_causal_edge_to_inferred(edge_dict)
        if inferred is None:
            continue
        key = (inferred.from_symbol, inferred.to_symbol)
        existing = converted.get(key)
        if existing is None or inferred.transition_probability > existing.transition_probability:
            converted[key] = inferred
    return list(converted.values())


# ═══════════════════════════════════════════════════════════════════════════
# Minimum connectivity enforcement
# ═══════════════════════════════════════════════════════════════════════════

def _build_heuristic_edges_from_tags(nodes: list[SymbolNode]) -> list[InferredEdge]:
    """Force-build edges from shared flow tags when no edges exist.

    Creates an edge between any two symbols that share at least one
    flow-trigger tag (same_flow_tag edges with medium weight).

    Semantic: Uses weighted locality instead of directory prefix.
    """
    edges: list[InferredEdge] = []
    seen: set[tuple[str, str]] = set()

    for a in nodes:
        for b in nodes:
            if a.symbol == b.symbol:
                continue
            key = (a.symbol, b.symbol)
            if key in seen:
                continue
            seen.add(key)

            # Check for overlapping flow-trigger tags
            shared_flow_tags = a.tags & b.tags & _FLOW_TRIGGER_TAGS
            if not shared_flow_tags:
                continue

            # Calculate tag overlap for the transition probability
            tag_overlap = _compute_tag_overlap(a.tags, b.tags)
            file_proximity = _compute_file_proximity(a.file_path, b.file_path)
            domain_sim = _compute_domain_similarity(a.domain, b.domain)

            # Semantic: Weighted locality scoring
            # class_similarity * 0.4 + module_similarity * 0.3 + package_similarity * 0.2 + import_similarity * 0.1
            # Note: import_similarity is approximated via domain_similarity here
            # (full import graph detection would require AST analysis)
            locality_score = (
                file_proximity * 0.4 +  # module/package proximity
                domain_sim * 0.3 +       # domain/import similarity
                tag_overlap * 0.3        # flow tag overlap
            )

            # Only create edge if locality score is meaningful
            if locality_score < 0.15:
                continue

            edges.append(InferredEdge(
                from_symbol=a.symbol,
                to_symbol=b.symbol,
                tag_overlap_score=tag_overlap,
                file_proximity_score=file_proximity,
                domain_similarity=domain_sim,
                transition_probability=min(locality_score * _SAME_FLOW_TAG_WEIGHT, 1.0),
                edge_type="shared_flow",
            ))

    return edges


def _enforce_minimum_connectivity(
    nodes: list[SymbolNode],
    edges: list[InferredEdge],
) -> list[InferredEdge]:
    """Ensure the edge set has at least one edge per node.

    If a node has no incoming or outgoing edges, force-build heuristic
    edges from shared flow tags.
    """
    if not nodes:
        return edges

    # Build adjacency from existing edges
    outgoing: dict[str, list[InferredEdge]] = {}
    incoming: dict[str, list[InferredEdge]] = {}
    for e in edges:
        outgoing.setdefault(e.from_symbol, []).append(e)
        incoming.setdefault(e.to_symbol, []).append(e)

    # Find nodes with no edges
    isolated = [
        n for n in nodes
        if n.symbol not in outgoing and n.symbol not in incoming
    ]
    if not isolated:
        return edges

    # Build heuristic edges for isolated nodes
    heuristic = _build_heuristic_edges_from_tags(isolated)
    # Also connect isolated nodes to the rest of the graph
    for iso in isolated:
        for n in nodes:
            if n.symbol == iso.symbol:
                continue
            shared = iso.tags & n.tags & _FLOW_TRIGGER_TAGS
            if not shared:
                continue
            key = (iso.symbol, n.symbol)
            if any(e.from_symbol == iso.symbol and e.to_symbol == n.symbol for e in edges):
                continue
            heuristic.append(InferredEdge(
                from_symbol=iso.symbol,
                to_symbol=n.symbol,
                tag_overlap_score=_compute_tag_overlap(iso.tags, n.tags),
                file_proximity_score=_compute_file_proximity(iso.file_path, n.file_path),
                domain_similarity=_compute_domain_similarity(iso.domain, n.domain),
                transition_probability=_SAME_FLOW_TAG_WEIGHT * 0.8,  # Slightly discounted for cross-node
                edge_type="shared_flow",
            ))

    return edges + heuristic


# ═══════════════════════════════════════════════════════════════════════════
# Main edge inference
# ═══════════════════════════════════════════════════════════════════════════

def infer_edges(
    nodes: list[SymbolNode],
    causal_edges: list[dict[str, Any]] | None = None,
) -> list[InferredEdge]:
    """Infer edges between all pairs of symbols.

    Merges two sources:
    1. Heuristic edges from co-tags + weighted locality + domain similarity
    2. Causal graph edges (when provided) — these are grounded edges
       from the static analysis engine (calls, shared_state, etc.)

    Edge types:
    - same file → strong edge (weight 0.7)
    - same flow tag → medium edge (weight 0.5)
    - same domain → weak edge (weight 0.3)
    - causal:{type} → grounded edge (weight based on causal type + confidence)

    Semantic: Uses weighted locality (same class/module/package/import)
    instead of naive directory prefix matching.

    Args:
        nodes: List of SymbolNode objects.
        causal_edges: Optional list of causal graph edge dicts.

    Returns:
        List of InferredEdge objects.
    """
    edges: list[InferredEdge] = []
    n = len(nodes)

    # ── Phase 1: Heuristic edges from tag/file/domain overlap ──
    for i in range(n):
        for j in range(i + 1, n):
            a, b = nodes[i], nodes[j]

            tag_overlap = _compute_tag_overlap(a.tags, b.tags)
            file_proximity = _compute_file_proximity(a.file_path, b.file_path)
            domain_sim = _compute_domain_similarity(a.domain, b.domain)

            # Semantic: Weighted locality scoring per spec
            # Score = class_similarity * 0.4 + module_similarity * 0.3 +
            #         package_similarity * 0.2 + import_similarity * 0.1
            # Note: import_similarity is approximated via domain_similarity
            locality_score = (
                file_proximity * 0.4 +  # class/module/package proximity
                domain_sim * 0.3 +       # import/domain similarity
                tag_overlap * 0.3        # flow tag overlap
            )

            # Only create edge if combined score exceeds threshold (> 0.5 per spec)
            if locality_score <= 0.5:
                continue

            # Determine edge type based on strongest signal
            if file_proximity >= 0.9:
                edge_type = "same_file"
                base_weight = _SAME_FILE_WEIGHT
            elif tag_overlap >= 0.3:
                edge_type = "same_flow_tag"
                base_weight = _SAME_FLOW_TAG_WEIGHT
            elif domain_sim >= 0.5:
                edge_type = "same_domain"
                base_weight = _SAME_DOMAIN_WEIGHT
            else:
                # Locality score passed but no dominant signal — use flow tag
                edge_type = "same_flow_tag"
                base_weight = _SAME_FLOW_TAG_WEIGHT

            # Transition probability = locality score * base weight
            transition_prob = locality_score * base_weight
            transition_prob = min(transition_prob, 1.0)

            if transition_prob < _STOP_THRESHOLD:
                continue

            # Create bidirectional edges
            edges.append(InferredEdge(
                from_symbol=a.symbol,
                to_symbol=b.symbol,
                tag_overlap_score=tag_overlap,
                file_proximity_score=file_proximity,
                domain_similarity=domain_sim,
                transition_probability=transition_prob,
                edge_type=edge_type,
            ))
            edges.append(InferredEdge(
                from_symbol=b.symbol,
                to_symbol=a.symbol,
                tag_overlap_score=tag_overlap,
                file_proximity_score=file_proximity,
                domain_similarity=domain_sim,
                transition_probability=transition_prob,
                edge_type=edge_type,
            ))

    # ── Semantic: Causal graph edges (grounded, directed) ──
    if causal_edges:
        causal_inferred = _convert_causal_edges(causal_edges)
        # Deduplicate: causal edges override heuristic edges for the same (from, to)
        existing_keys: set[tuple[str, str]] = {
            (e.from_symbol, e.to_symbol) for e in edges
        }
        for ce in causal_inferred:
            key = (ce.from_symbol, ce.to_symbol)
            if key not in existing_keys:
                existing_keys.add(key)
                edges.append(ce)

    # ── Phase 3: Minimum connectivity enforcement ──
    # If we still have no edges at all, force-build from shared flow tags
    if not edges:
        edges = _build_heuristic_edges_from_tags(nodes)

    # Ensure every node has at least one connection
    edges = _enforce_minimum_connectivity(nodes, edges)

    return edges


# ═══════════════════════════════════════════════════════════════════════════
# Step 2: Build adjacency from edges
# ═══════════════════════════════════════════════════════════════════════════

def _build_adjacency(
    edges: list[InferredEdge],
) -> dict[str, list[InferredEdge]]:
    """Build adjacency list from inferred edges."""
    adj: dict[str, list[InferredEdge]] = {}
    for edge in edges:
        adj.setdefault(edge.from_symbol, []).append(edge)
    return adj


# ═══════════════════════════════════════════════════════════════════════════
# Step 3: Simulate propagation (BFS with decay)
# ═══════════════════════════════════════════════════════════════════════════

def simulate_propagation(
    start_symbol: str,
    adjacency: dict[str, list[InferredEdge]],
    max_steps: int = 5,
    stop_threshold: float = _STOP_THRESHOLD,
    decay: float = _DECAY_PER_HOP,
) -> list[FailureChain]:
    """Run BFS with decay from a start symbol.

    Args:
        start_symbol: The symbol to start propagation from.
        adjacency: Adjacency list (symbol → list of InferredEdge).
        max_steps: Maximum propagation depth.
        stop_threshold: Minimum probability to continue.
        decay: Probability decay per hop.

    Returns:
        List of FailureChain objects (sorted by total probability).
    """
    chains: list[FailureChain] = []
    visited_paths: set[str] = set()

    # BFS queue: (current_symbol, path, probabilities, current_probability)
    queue: deque[tuple[str, list[str], list[float], float]] = deque()
    queue.append((start_symbol, [start_symbol], [1.0], 1.0))

    while queue:
        current, path, probs, current_prob = queue.popleft()

        if len(path) > 1:
            # Record this path as a chain
            path_key = "→".join(path)
            if path_key not in visited_paths:
                visited_paths.add(path_key)
                chains.append(FailureChain(
                    path=list(path),
                    probabilities=list(probs),
                    total_probability=current_prob,
                    steps=len(path) - 1,
                ))

        if len(path) >= max_steps:
            continue

        for edge in adjacency.get(current, []):
            if edge.to_symbol in path:
                continue  # Avoid cycles

            # Apply decay
            hop_prob = edge.transition_probability * decay
            new_prob = current_prob * hop_prob

            if new_prob < stop_threshold:
                continue

            new_path = path + [edge.to_symbol]
            new_probs = probs + [hop_prob]

            queue.append((edge.to_symbol, new_path, new_probs, new_prob))

    # Sort by total probability (highest first)
    chains.sort(key=lambda c: -c.total_probability)
    return chains


# ═══════════════════════════════════════════════════════════════════════════
# Step 4: Generate failure chains
# ═══════════════════════════════════════════════════════════════════════════

_FAILURE_CLASS_PATTERNS: list[tuple[set[str], str]] = [
    ({"payment", "charge", "double"}, "double_charge"),
    ({"tax", "vat", "gst", "calculation"}, "tax_mismatch"),
    ({"state", "status", "transition"}, "state_inconsistency"),
    ({"order", "duplicate", "idempotency"}, "idempotency_break"),
    ({"invoice", "render", "pdf"}, "rendering_drift"),
    ({"auth", "permission", "access"}, "permission_escalation"),
    ({"cache", "stale", "invalidation"}, "stale_cache"),
    ({"notification", "email", "delivery"}, "notification_silence"),
    ({"checkout", "flow", "break"}, "checkout_flow_break"),
    ({"subscription", "renewal", "cycle"}, "subscription_cycle_error"),
    ({"webhook", "callback", "event"}, "webhook_mismatch"),
    ({"inventory", "stock", "oversell"}, "stock_desync"),
    ({"fulfillment", "delay", "ship"}, "fulfillment_delay"),
    ({"discount", "coupon", "pricing"}, "pricing_error"),
]


def _classify_failure_chain(path: list[str], tags: dict[str, set[str]]) -> str:
    """Classify a failure chain into a failure class based on path symbols and tags."""
    path_text = " ".join(s.lower() for s in path)
    for tag_set, failure_class in _FAILURE_CLASS_PATTERNS:
        if any(t in path_text for t in tag_set):
            return failure_class
    return "state_inconsistency"


def _build_chain_description(path: list[str], failure_class: str) -> str:
    """Build a human-readable description of a failure chain."""
    path_str = " → ".join(path)
    return f"[{failure_class}] {path_str}"


def generate_failure_chains(
    nodes: list[SymbolNode],
    max_chains: int = 10,
    max_steps: int = 5,
    causal_edges: list[dict[str, Any]] | None = None,
) -> list[FailureChain]:
    """Generate failure chains from a set of symbol nodes.

    Full pipeline:
    1. Infer edges from co-tags + file proximity + domain similarity + causal edges
    2. Build adjacency
    3. Run BFS with decay from each node
    4. Collect and rank chains

    Args:
        nodes: List of SymbolNode objects.
        max_chains: Maximum number of chains to return.
        max_steps: Maximum propagation depth.
        causal_edges: Optional list of causal graph edge dicts to merge in.

    Returns:
        List of FailureChain objects (sorted by total probability).
    """
    if not nodes:
        return []

    # Step 1: Infer edges (heuristic + causal)
    edges = infer_edges(nodes, causal_edges=causal_edges)

    # Step 2: Build adjacency
    adjacency = _build_adjacency(edges)

    # Step 3: Simulate propagation from each node
    all_chains: list[FailureChain] = []
    seen_paths: set[str] = set()

    for node in nodes:
        chains = simulate_propagation(
            start_symbol=node.symbol,
            adjacency=adjacency,
            max_steps=max_steps,
        )
        for chain in chains:
            path_key = "→".join(chain.path)
            if path_key not in seen_paths:
                seen_paths.add(path_key)
                # Classify and describe
                tags_map: dict[str, set[str]] = {n.symbol: n.tags for n in nodes}
                chain.failure_class = _classify_failure_chain(chain.path, tags_map)
                chain.description = _build_chain_description(chain.path, chain.failure_class)
                all_chains.append(chain)

    # Sort by total probability (highest first)
    all_chains.sort(key=lambda c: -c.total_probability)
    return all_chains[:max_chains]


# ═══════════════════════════════════════════════════════════════════════════
# Convenience: build from enriched files
# ═══════════════════════════════════════════════════════════════════════════

def _classify_node_type(symbol: str, file_path: str) -> str:
    """Classify a symbol as 'runtime' or 'test' based on path and naming.

    Phase 1: Test pollution removal.
    """
    # Check if path contains "/tests/"
    if "/tests/" in file_path or "/test_" in file_path:
        return "test"
    # Check symbol name prefixes
    if _is_test_or_mock_symbol(symbol):
        return "test"
    return "runtime"


def build_symbol_nodes_from_enriched_files(
    enriched_files: list[dict],
    causal_edges: list[dict[str, Any]] | None = None,
) -> list[SymbolNode]:
    """Build SymbolNodes from enriched file data.

    Also extracts call relationships from hunk lines to enrich node tags
    with caller/callee information, giving the edge inference engine more
    signal even when causal edges are not provided.

    Phase 1: Classifies nodes as 'runtime' or 'test' and filters test nodes
    from the graph. Only runtime nodes are returned.

    Args:
        enriched_files: List of enriched file dicts.
        causal_edges: Optional causal edges to extract additional signal.

    Returns:
        List of runtime SymbolNode objects (test nodes excluded).
    """
    nodes: list[SymbolNode] = []
    seen: set[str] = set()
    coverage_map: dict[str, list[str]] = {}  # runtime_symbol → linked_tests

    for file_data in enriched_files:
        file_path = file_data.get("file_path", "")
        for fn in file_data.get("changed_functions", []) or []:
            fn_data = fn if isinstance(fn, dict) else {}
            symbol = fn_data.get("name", "")
            if not symbol or symbol in seen:
                continue
            seen.add(symbol)

            # Phase 1: Classify node type
            node_type = _classify_node_type(symbol, file_path)

            # Skip test nodes — they are noise for runtime graph construction
            if node_type == "test":
                continue

            # Collect tags
            tags: set[str] = set()
            for signal in file_data.get("keyword_signals", []) or []:
                signal_text = signal.keyword if hasattr(signal, "keyword") else str(signal)
                tags.add(signal_text.lower())

            # Extract call relationships from hunk lines to enrich tags
            for hunk in file_data.get("hunks", []) or []:
                hunk_data = hunk if isinstance(hunk, dict) else {}
                for raw_line in hunk_data.get("lines", []) or []:
                    line_data = raw_line if isinstance(raw_line, dict) else {}
                    content = str(line_data.get("content", "")).strip()
                    if not content or content.startswith("#"):
                        continue
                    # Detect function calls in the line
                    import re
                    calls = re.findall(r'([a-zA-Z_][a-zA-Z0-9_]*)\s*\(', content)
                    for called in calls:
                        if called not in ("self", "cls", "super", "if", "for", "while", "with",
                                         "return", "raise", "import", "from", "as", "try",
                                         "except", "elif", "else", "pass", "print"):
                            tags.add(f"calls:{called}")
                            # Phase 1: Track test coverage — if this runtime symbol
                            # is called from a test file, record the relationship
                            if _is_test_or_mock_symbol(called):
                                coverage_map.setdefault(symbol, []).append(called)

            # Infer domain
            from core_engine.risk_scoring_engine import _infer_domain
            domain = _infer_domain(symbol, file_path, list(tags))
            domain_region = _DOMAIN_REGIONS.get(domain, "general")

            nodes.append(SymbolNode(
                symbol=symbol,
                file_path=file_path,
                tags=tags,
                domain=domain,
                domain_region=domain_region,
                node_type=node_type,
            ))

    # If causal edges are available, also add symbols referenced in edges
    # that aren't in the enriched files but appear as edge targets
    if causal_edges:
        edge_symbols: set[str] = set()
        for e in causal_edges:
            from_sym = e.get("from", "")
            to_sym = e.get("to", "")
            if from_sym and from_sym not in seen:
                edge_symbols.add(from_sym)
            if to_sym and to_sym not in seen:
                edge_symbols.add(to_sym)

        for sym in edge_symbols:
            if sym not in seen:
                seen.add(sym)
                # Skip test nodes from causal edges too
                node_type = _classify_node_type(sym, "")
                if node_type == "test":
                    continue
                # Minimal node — no file path or tags since it wasn't in the diff
                from core_engine.risk_scoring_engine import _infer_domain
                domain = _infer_domain(sym, "", [])
                domain_region = _DOMAIN_REGIONS.get(domain, "general")
                nodes.append(SymbolNode(
                    symbol=sym,
                    file_path="",
                    tags=set(),
                    domain=domain,
                    domain_region=domain_region,
                    node_type=node_type,
                ))

    # Store coverage map for downstream consumers (e.g., coverage engine)
    # This is accessible via the module-level variable or can be returned
    # in the run_failure_simulation() result
    build_symbol_nodes_from_enriched_files._last_coverage_map = coverage_map  # type: ignore[attr-defined]

    return nodes


def run_failure_simulation(
    enriched_files: list[dict],
    max_chains: int = 10,
    max_steps: int = 5,
    causal_edges: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run the full failure simulation pipeline.

    Args:
        enriched_files: Enriched file data from orchestrator.
        max_chains: Maximum number of failure chains to return.
        max_steps: Maximum propagation depth.
        causal_edges: Optional causal graph edges to merge in.

    Returns:
        Dict with 'failure_chains', 'edges', 'nodes', and 'coverage_map' keys.
    """
    nodes = build_symbol_nodes_from_enriched_files(enriched_files, causal_edges=causal_edges)
    edges = infer_edges(nodes, causal_edges=causal_edges)
    chains = generate_failure_chains(
        nodes,
        max_chains=max_chains,
        max_steps=max_steps,
        causal_edges=causal_edges,
    )

    # Phase 1: Retrieve coverage map (runtime_symbol → linked_tests)
    coverage_map = getattr(build_symbol_nodes_from_enriched_files, '_last_coverage_map', {})

    return {
        "failure_chains": [c.to_dict() for c in chains],
        "inferred_edges": [e.to_dict() for e in edges],
        "symbol_nodes": [n.to_dict() for n in nodes],
        "total_chains": len(chains),
        "total_edges": len(edges),
        "total_nodes": len(nodes),
        "coverage_map": coverage_map,  # Phase 1: runtime_symbol → linked_tests
    }

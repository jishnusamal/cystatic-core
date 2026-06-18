"""
Risk Scoring Engine — deterministic, non-LLM risk computation.

Two mechanisms:
(A) Risk Scoring Function — per-symbol risk_score based on:
    risk_score = impact_weight × flow_centrality × state_mutation_penalty × cross_domain_factor

(B) Risk Clustering Engine — hierarchical clustering on impact overlap
    Merges 20 anchors → 3 deterministic risk clusters.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import itertools


# ── Domain base multipliers ──────────────────────────────────────────────
_DOMAIN_IMPACT_WEIGHT: dict[str, float] = {
    "billing": 0.7,
    "billing_core": 0.65,
    "billing_output": 0.6,
    "billing_calculation": 0.7,
    "billing_pricing": 0.6,
    "billing_cart": 0.6,
    "billing_recurring": 0.65,
    "money_movement": 0.8,
    "payment": 0.8,
    "order": 0.6,
    "invoice": 0.65,
    "tax": 0.7,
    "checkout": 0.75,
    "fulfillment": 0.5,
    "inventory": 0.5,
    "catalog": 0.4,
    "identity": 0.6,
    "auth": 0.6,
    "subscription": 0.65,
    "notification": 0.3,
    "cache": 0.2,
    "general": 0.2,
}

_STATE_MUTATION_MULTIPLIER: float = 2.5
_MONEY_FLOW_MULTIPLIER: float = 1.8
_TAX_FLOW_MULTIPLIER: float = 1.6
_CROSS_DOMAIN_MULTIPLIER: float = 1.4

# Tag categories used for centrality and fanout estimation
_FLOW_TAGS: set[str] = {
    "payment", "charge", "refund", "payout", "transaction",
    "invoice", "receipt", "debit", "credit",
}

_MONEY_TAGS: set[str] = {
    "money", "currency", "amount", "price", "cost", "fee",
    "total", "subtotal", "discount", "tax_amount", "shipping_cost",
}

_TAX_TAGS: set[str] = {
    "tax", "vat", "gst", "sales_tax", "withholding",
}

_STATE_MUTATION_TAGS: set[str] = {
    "state", "status", "flag", "transition",
    "set_", "update_", "mark_", "toggle",
    "save", "persist", "commit", "flush",
}

# Global fanout estimation — how many other symbols typically depend on
# each category of symbol. These are priors, not per-file counts.
_FANOUT_PRIORS: dict[str, int] = {
    "payment_processor": 12,
    "tax_calculator": 8,
    "discount_engine": 6,
    "checkout_flow": 10,
    "order_creator": 8,
    "invoice_generator": 6,
    "auth_middleware": 15,
    "price_service": 9,
    "shipping_calculator": 5,
    "notification_sender": 4,
    "cache_service": 20,
    "default": 3,
}


@dataclass
class RiskScoreResult:
    """Per-symbol risk score with breakdown."""
    symbol: str
    domain: str
    impact_weight: float
    flow_centrality: float
    state_mutation_penalty: float
    cross_domain_factor: float
    fanout_estimate: int
    risk_score: float
    signals: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "domain": self.domain,
            "impact_weight": round(self.impact_weight, 3),
            "flow_centrality": round(self.flow_centrality, 3),
            "state_mutation_penalty": round(self.state_mutation_penalty, 3),
            "cross_domain_factor": round(self.cross_domain_factor, 3),
            "fanout_estimate": self.fanout_estimate,
            "risk_score": round(self.risk_score, 4),
            "signals": self.signals,
        }


def _infer_domain(symbol: str, file_path: str, tags: list[str]) -> str:
    """Infer domain from symbol name, file path, and tags."""
    combined = f"{symbol.lower()} {file_path.lower()} {' '.join(t.lower() for t in tags)}"
    # Check explicit domain matches
    for domain in _DOMAIN_IMPACT_WEIGHT:
        if domain in combined:
            return domain
    # Check broader patterns
    if any(m in combined for m in ["money", "payment", "pay", "charge"]):
        return "money_movement"
    if "tax" in combined or "vat" in combined or "gst" in combined:
        return "tax"
    if "checkout" in combined:
        return "checkout"
    if "order" in combined:
        return "order"
    if "invoice" in combined:
        return "invoice"
    if "auth" in combined or "login" in combined or "session" in combined:
        return "auth"
    return "general"


def _compute_flow_centrality(symbol: str, tags: list[str], file_path: str) -> float:
    """Compute how central this symbol is to money/tax flows (0.0–1.0)."""
    combined = f"{symbol.lower()} {' '.join(t.lower() for t in tags)} {file_path.lower()}"
    score = 0.0

    # Direct flow tag match
    for tag in _FLOW_TAGS:
        if tag in combined:
            score += 0.3
            break

    # Money-related tags
    for tag in _MONEY_TAGS:
        if tag in combined:
            score += 0.2

    # Tax-related tags
    for tag in _TAX_TAGS:
        if tag in combined:
            score += 0.2

    # File path signals
    if any(p in file_path.lower() for p in ["payment", "billing", "checkout", "order", "invoice", "tax"]):
        score += 0.2

    return min(score, 1.0)


def _has_state_mutation(tags: list[str], symbol: str, hunks: list[dict] | None = None) -> bool:
    """Detect if this symbol performs state mutations."""
    combined = f"{symbol.lower()} {' '.join(t.lower() for t in tags)}"

    for tag in _STATE_MUTATION_TAGS:
        if tag in combined:
            return True

    # Also scan hunk lines for state-mutation patterns
    if hunks:
        for hunk in hunks:
            lines = hunk.get("lines", []) if isinstance(hunk, dict) else []
            for line in lines:
                content = line.get("content", "") if isinstance(line, dict) else str(line)
                lower = content.lower()
                if any(p in lower for p in [
                    ".save(", ".update(", ".delete(", ".commit(",
                    "insert(", "update ", "delete from",
                    "state =", "status =",
                ]):
                    return True

    return False


def _compute_fanout(symbol: str, tags: list[str], file_path: str) -> int:
    """Estimate how many other symbols depend on this symbol."""
    combined = f"{symbol.lower()} {file_path.lower()}"
    for pattern, fanout in _FANOUT_PRIORS.items():
        if pattern in combined:
            return fanout
    return _FANOUT_PRIORS["default"]


def _compute_cross_domain_factor(tags: list[str]) -> float:
    """Compute cross-domain factor: how many distinct domains does this touch?"""
    domains_touched: set[str] = set()
    combined = " ".join(t.lower() for t in tags)
    for domain in _DOMAIN_IMPACT_WEIGHT:
        if domain in combined:
            domains_touched.add(domain)
    # At least 2 distinct domains → apply multiplier
    if len(domains_touched) >= 2:
        return _CROSS_DOMAIN_MULTIPLIER
    return 1.0


# ═══════════════════════════════════════════════════════════════════════════
# (A) Risk Scoring Function
# ═══════════════════════════════════════════════════════════════════════════

def compute_risk_score(
    symbol: str,
    file_path: str = "",
    tags: list[str] | None = None,
    hunks: list[dict] | None = None,
    impact_weight_override: float | None = None,
) -> RiskScoreResult:
    """Compute risk score for a single symbol.

    risk_score = impact_weight × flow_centrality × state_mutation_penalty × cross_domain_factor

    The fanout estimate is returned as metadata (not part of the product)
    so the caller can use it for downstream weighting.

    Args:
        symbol: The symbol name (e.g., function name).
        file_path: Full file path for domain inference.
        tags: Semantic tags (e.g., from keyword_signals).
        hunks: Diff hunks for state-mutation detection.
        impact_weight_override: Override domain-based impact weight.

    Returns:
        RiskScoreResult with full breakdown.
    """
    tags = tags or []
    domain = _infer_domain(symbol, file_path, tags)

    impact_weight = impact_weight_override or _DOMAIN_IMPACT_WEIGHT.get(domain, 0.2)
    flow_centrality = _compute_flow_centrality(symbol, tags, file_path)
    has_mutation = _has_state_mutation(tags, symbol, hunks)
    state_mutation_penalty = _STATE_MUTATION_MULTIPLIER if has_mutation else 1.0
    cross_domain_factor = _compute_cross_domain_factor(tags)
    fanout_estimate = _compute_fanout(symbol, tags, file_path)

    risk_score = impact_weight * flow_centrality * state_mutation_penalty * cross_domain_factor

    signals: dict[str, Any] = {
        "has_state_mutation": has_mutation,
        "money_flow": flow_centrality >= 0.3 and any(t in " ".join(t.lower() for t in tags) for t in _MONEY_TAGS),
        "tax_flow": any(t.lower() in " ".join(t.lower() for t in tags) for t in _TAX_TAGS),
        "domain": domain,
    }

    return RiskScoreResult(
        symbol=symbol,
        domain=domain,
        impact_weight=impact_weight,
        flow_centrality=flow_centrality,
        state_mutation_penalty=state_mutation_penalty,
        cross_domain_factor=cross_domain_factor,
        fanout_estimate=fanout_estimate,
        risk_score=risk_score,
        signals=signals,
    )


def compute_batch_risk_scores(
    symbols: list[dict],
) -> list[RiskScoreResult]:
    """Compute risk scores for a batch of symbols.

    Each symbol dict may have:
        - symbol (str): required
        - file_path (str): optional
        - tags (list[str]): optional
        - hunks (list[dict]): optional

    Returns sorted list (highest risk first).
    """
    results: list[RiskScoreResult] = []
    for entry in symbols:
        if not entry.get("symbol"):
            continue
        result = compute_risk_score(
            symbol=entry["symbol"],
            file_path=entry.get("file_path", ""),
            tags=entry.get("tags", []),
            hunks=entry.get("hunks"),
        )
        results.append(result)

    results.sort(key=lambda r: -r.risk_score)
    return results


# ═══════════════════════════════════════════════════════════════════════════
# (B) Risk Clustering Engine — hierarchical clustering on impact overlap
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class RiskCluster:
    """A cluster of related risk symbols."""
    cluster_id: int
    symbols: list[str]
    shared_downstream_nodes: list[str] = field(default_factory=list)
    shared_tags: list[str] = field(default_factory=list)
    shared_domain_region: str = ""
    combined_risk_score: float = 0.0
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "cluster_id": self.cluster_id,
            "symbols": self.symbols,
            "shared_downstream_nodes": self.shared_downstream_nodes,
            "shared_tags": self.shared_tags,
            "shared_domain_region": self.shared_domain_region,
            "combined_risk_score": round(self.combined_risk_score, 4),
            "description": self.description,
        }


def _jaccard_similarity(set_a: set[str], set_b: set[str]) -> float:
    """Jaccard similarity between two sets."""
    if not set_a and not set_b:
        return 1.0
    if not set_a or not set_b:
        return 0.0
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union)


def _impact_overlap_score(
    a_tags: set[str],
    b_tags: set[str],
    a_downstream: set[str],
    b_downstream: set[str],
    a_domain: str,
    b_domain: str,
) -> float:
    """Compute impact overlap score between two anchors (0.0–1.0).

    Combines:
    - tag overlap (weight 0.3)
    - shared downstream nodes (weight 0.4)
    - shared domain (weight 0.3)
    """
    tag_sim = _jaccard_similarity(a_tags, b_tags)
    downstream_sim = _jaccard_similarity(a_downstream, b_downstream)
    domain_sim = 1.0 if a_domain == b_domain else 0.0

    score = (
        tag_sim * 0.3 +
        downstream_sim * 0.4 +
        domain_sim * 0.3
    )
    return score


@dataclass
class AnchorNode:
    """A risk anchor — a symbol with its context for clustering."""
    symbol: str
    tags: set[str] = field(default_factory=set)
    downstream_nodes: set[str] = field(default_factory=set)
    domain: str = "general"
    risk_score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "tags": sorted(self.tags),
            "downstream_nodes": sorted(self.downstream_nodes),
            "domain": self.domain,
            "risk_score": round(self.risk_score, 4),
        }


def build_risk_clusters(
    anchors: list[AnchorNode],
    target_clusters: int = 3,
    similarity_threshold: float = 0.15,
) -> list[RiskCluster]:
    """Hierarchical clustering on impact overlap.

    Merges N anchors into `target_clusters` clusters using average-linkage
    hierarchical clustering.

    Args:
        anchors: List of AnchorNode objects to cluster.
        target_clusters: Desired number of output clusters (default 3).
        similarity_threshold: Minimum similarity to consider merging.

    Returns:
        List of RiskCluster objects (deterministic, sorted by combined risk).
    """
    if not anchors:
        return []

    # Convert to mutable cluster state
    clusters: list[set[int]] = [{i} for i in range(len(anchors))]

    # Precompute pairwise similarity matrix
    n = len(anchors)
    sim_matrix: dict[tuple[int, int], float] = {}
    for i in range(n):
        for j in range(i + 1, n):
            score = _impact_overlap_score(
                a_tags=anchors[i].tags,
                b_tags=anchors[j].tags,
                a_downstream=anchors[i].downstream_nodes,
                b_downstream=anchors[j].downstream_nodes,
                a_domain=anchors[i].domain,
                b_domain=anchors[j].domain,
            )
            sim_matrix[(i, j)] = score

    # Hierarchical merging (average-linkage)
    while len(clusters) > target_clusters:
        best_i, best_j = -1, -1
        best_score = -1.0

        for idx_i in range(len(clusters)):
            for idx_j in range(idx_i + 1, len(clusters)):
                # Average-linkage: mean pairwise similarity between clusters
                scores: list[float] = []
                for elem_i in clusters[idx_i]:
                    for elem_j in clusters[idx_j]:
                        a, b = min(elem_i, elem_j), max(elem_i, elem_j)
                        s = sim_matrix.get((a, b), 0.0)
                        scores.append(s)
                avg_score = sum(scores) / len(scores) if scores else 0.0

                if avg_score > best_score and avg_score >= similarity_threshold:
                    best_score = avg_score
                    best_i, best_j = idx_i, idx_j

        if best_i == -1:
            # No more mergable clusters — stop early
            break

        # Merge best_j into best_i, remove best_j
        clusters[best_i] |= clusters[best_j]
        clusters.pop(best_j)

    # Build RiskCluster objects
    result: list[RiskCluster] = []
    for cluster_id, cluster_indices in enumerate(clusters):
        symbols_in_cluster = [anchors[i].symbol for i in sorted(cluster_indices)]
        all_tags: set[str] = set()
        all_downstream: set[str] = set()
        domains: set[str] = set()
        combined_risk = 0.0

        for i in cluster_indices:
            all_tags |= anchors[i].tags
            all_downstream |= anchors[i].downstream_nodes
            domains.add(anchors[i].domain)
            combined_risk += anchors[i].risk_score

        # Determine dominant domain
        dominant_domain = max(domains, key=lambda d: _DOMAIN_IMPACT_WEIGHT.get(d, 0.0)) if domains else "general"

        # Build description
        description = _build_cluster_description(dominant_domain, symbols_in_cluster, all_tags)

        result.append(RiskCluster(
            cluster_id=cluster_id,
            symbols=symbols_in_cluster,
            shared_downstream_nodes=sorted(all_downstream),
            shared_tags=sorted(all_tags),
            shared_domain_region=dominant_domain,
            combined_risk_score=combined_risk,
            description=description,
        ))

    # Sort by combined risk (highest first)
    result.sort(key=lambda c: -c.combined_risk_score)
    return result


def _build_cluster_description(domain: str, symbols: list[str], tags: set[str]) -> str:
    """Build a human-readable cluster description."""
    tag_str = ", ".join(sorted(tags)[:5])
    symbol_str = ", ".join(symbols[:5])

    if domain == "money_movement" or domain == "payment":
        return f"Payment flow risk affecting {symbol_str}. Tags: {tag_str}"
    elif domain == "tax":
        return f"Tax calculation risk affecting {symbol_str}. Tags: {tag_str}"
    elif domain == "checkout":
        return f"Checkout flow risk affecting {symbol_str}. Tags: {tag_str}"
    elif domain == "order":
        return f"Order processing risk affecting {symbol_str}. Tags: {tag_str}"
    elif domain == "invoice":
        return f"Invoice generation risk affecting {symbol_str}. Tags: {tag_str}"
    elif domain == "billing":
        return f"Billing system risk affecting {symbol_str}. Tags: {tag_str}"
    else:
        return f"Change risk in {domain} affecting {symbol_str}. Tags: {tag_str}"


# ═══════════════════════════════════════════════════════════════════════════
# Convenience: build anchors from enriched files
# ═══════════════════════════════════════════════════════════════════════════

def build_anchors_from_enriched_files(
    enriched_files: list[dict],
    downstream_map: dict[str, list[str]] | None = None,
) -> list[AnchorNode]:
    """Build AnchorNodes from enriched file data.

    Args:
        enriched_files: List of enriched file dicts (from orchestrator).
        downstream_map: Optional map of symbol → list of downstream symbols.
            If provided, each anchor gets its downstream nodes populated.

    Returns:
        List of AnchorNode objects.
    """
    anchors: list[AnchorNode] = []
    downstream_map = downstream_map or {}

    for file_data in enriched_files:
        file_path = file_data.get("file_path", "")
        for fn in file_data.get("changed_functions", []) or []:
            fn_data = fn if isinstance(fn, dict) else {}
            symbol = fn_data.get("name", "")
            if not symbol:
                continue

            # Collect tags from keyword_signals
            tags: set[str] = set()
            for signal in file_data.get("keyword_signals", []) or []:
                signal_text = signal.keyword if hasattr(signal, "keyword") else str(signal)
                tags.add(signal_text.lower())

            # Add file-path-based tags
            for keyword in ["payment", "billing", "checkout", "order", "invoice", "tax", "auth", "cart"]:
                if keyword in file_path.lower():
                    tags.add(keyword)

            # Compute risk score
            risk_result = compute_risk_score(
                symbol=symbol,
                file_path=file_path,
                tags=list(tags),
                hunks=file_data.get("hunks"),
            )

            # Get downstream nodes
            downstream = set(downstream_map.get(symbol, []))

            anchors.append(AnchorNode(
                symbol=symbol,
                tags=tags,
                downstream_nodes=downstream,
                domain=risk_result.domain,
                risk_score=risk_result.risk_score,
            ))

    return anchors


def compute_risk_summary(
    enriched_files: list[dict],
    downstream_map: dict[str, list[str]] | None = None,
    target_clusters: int = 3,
) -> dict[str, Any]:
    """Full risk summary: scoring + clustering.

    Args:
        enriched_files: Enriched file data from orchestrator.
        downstream_map: Symbol → downstream symbols map.
        target_clusters: Number of clusters to produce.

    Returns:
        Dict with 'risk_scores' and 'clusters' keys.
    """
    anchors = build_anchors_from_enriched_files(enriched_files, downstream_map)
    risk_scores = [a.risk_score for a in anchors]
    clusters = build_risk_clusters(anchors, target_clusters=target_clusters)

    # Build RiskScoreResult-like dicts from anchors for backward compatibility
    risk_score_dicts = []
    for anchor in anchors:
        risk_score_dicts.append({
            "symbol": anchor.symbol,
            "domain": anchor.domain,
            "impact_weight": 0.0,
            "flow_centrality": 0.0,
            "state_mutation_penalty": 0.0,
            "cross_domain_factor": 0.0,
            "fanout_estimate": 0,
            "risk_score": anchor.risk_score,
            "signals": {"domain": anchor.domain},
        })

    return {
        "anchors": [a.to_dict() for a in anchors],
        "risk_scores": risk_score_dicts,
        "clusters": [c.to_dict() for c in clusters],
        "total_anchors": len(anchors),
        "total_clusters": len(clusters),
        "overall_risk_level": _compute_overall_risk_level(clusters),
    }


def _compute_overall_risk_level(clusters: list[RiskCluster]) -> str:
    """Compute overall risk level from clusters."""
    if not clusters:
        return "LOW"
    max_risk = max(c.combined_risk_score for c in clusters)
    # Scale: risk_score can be up to ~3.0 (1.0 * 1.0 * 2.5 * 1.4)
    # Map: >1.5 → HIGH, >0.5 → MEDIUM, else LOW
    if max_risk > 1.5:
        return "HIGH"
    elif max_risk > 0.5:
        return "MEDIUM"
    return "LOW"
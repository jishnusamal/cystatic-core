"""
Layer 2 — Impact Evidence Collection (Probabilistic Structure)

Bridges the gap between change signals (Layer 1) and failure scenarios.

These are NOT truth, NOT hallucination, NOT execution guarantees.
They are "likely propagation structure" — weak signals the LLM can use
to reason even when execution paths are sparse.

Rules (deterministic):
  RULE 1 — CANONICAL FLOW (strongest): hardcoded pipeline
    checkout → order → invoice → tax → payment → ledger
  RULE 2 — SYMBOL TOKEN MATCH: shared tokens connect symbols
  RULE 3 — CHANGE CO-LOCATION: multiple modified symbols in same file → weakly connect
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ══════════════════════════════════════════════════════════════════════════════
# Evidence Strength
# ══════════════════════════════════════════════════════════════════════════════

class EvidenceStrength(Enum):
    STRONG = "STRONG"
    MEDIUM = "MEDIUM"
    WEAK = "WEAK"


# ══════════════════════════════════════════════════════════════════════════════
# Evidence Types & Hierarchy
# ══════════════════════════════════════════════════════════════════════════════

# Strong evidence (0.7–0.95)
STRONG_EVIDENCE_TYPES: set[str] = {
    "shared_class",
    "shared_module",
    "import_reference",
    "ast_reference",
    "symbol_reference",
}

# Medium evidence (0.5–0.7)
MEDIUM_EVIDENCE_TYPES: set[str] = {
    "shared_business_object",
    "shared_domain",
    "risk_tag_association",
}

# Weak evidence (0.2–0.4)
WEAK_EVIDENCE_TYPES: set[str] = {
    "canonical_flow",
    "naming_similarity",
    "shared_file",
}

EVIDENCE_TYPES: set[str] = STRONG_EVIDENCE_TYPES | MEDIUM_EVIDENCE_TYPES | WEAK_EVIDENCE_TYPES

# Confidence ranges by strength
EVIDENCE_STRENGTH_RANGES: dict[EvidenceStrength, tuple[float, float]] = {
    EvidenceStrength.STRONG: (0.7, 0.95),
    EvidenceStrength.MEDIUM: (0.5, 0.7),
    EvidenceStrength.WEAK: (0.2, 0.4),
}

# Evidence type → strength mapping
_EVIDENCE_TYPE_STRENGTH: dict[str, EvidenceStrength] = {
    t: EvidenceStrength.STRONG for t in STRONG_EVIDENCE_TYPES
}
_EVIDENCE_TYPE_STRENGTH.update({t: EvidenceStrength.MEDIUM for t in MEDIUM_EVIDENCE_TYPES})
_EVIDENCE_TYPE_STRENGTH.update({t: EvidenceStrength.WEAK for t in WEAK_EVIDENCE_TYPES})


def get_evidence_strength(evidence_type: str) -> EvidenceStrength:
    """Get the strength level for an evidence type."""
    return _EVIDENCE_TYPE_STRENGTH.get(evidence_type, EvidenceStrength.WEAK)


# Mapping from old source names to new evidence types
_SOURCE_TO_EVIDENCE_TYPE: dict[str, str] = {
    "domain_flow": "canonical_flow",
    "shared_service": "shared_file",
    "naming": "naming_similarity",
}


# ══════════════════════════════════════════════════════════════════════════════
# Data Structures
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class ImpactEvidence:
    """A piece of evidence connecting two symbols."""
    source_symbol: str
    target_symbol: str
    evidence_type: str = "canonical_flow"
    confidence: float = 0.2  # 0.2–0.6 range
    explanation: str = ""
    metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_symbol": self.source_symbol,
            "target_symbol": self.target_symbol,
            "evidence_type": self.evidence_type,
            "confidence": round(self.confidence, 3),
            "explanation": self.explanation,
        }

    @property
    def strength(self) -> EvidenceStrength:
        return get_evidence_strength(self.evidence_type)


@dataclass
class EvidenceCluster:
    """A clustered group of evidence sharing a common theme.

    Instead of N×M individual evidence records, group by theme
    so the LLM sees a single coherent signal.
    """
    theme: str
    sources: list[str]
    targets: list[str]
    confidence: float
    explanation: str
    evidence_types: list[str] = field(default_factory=list)
    evidence_strength: str = "WEAK"

    def to_dict(self) -> dict[str, Any]:
        return {
            "theme": self.theme,
            "sources": sorted(set(self.sources)),
            "targets": sorted(set(self.targets)),
            "confidence": round(self.confidence, 3),
            "explanation": self.explanation,
            "evidence_strength": self.evidence_strength,
        }


@dataclass
class EvidenceSummary:
    """Synthesized evidence summary for the LLM.

    The deterministic engine answers "what appears involved?"
    before the LLM sees anything.
    """
    risk_area: str
    confidence: float
    evidence: list[str]
    supporting_symbols: list[str] = field(default_factory=list)
    evidence_strength: str = "WEAK"

    def to_dict(self) -> dict[str, Any]:
        return {
            "risk_area": self.risk_area,
            "confidence": round(self.confidence, 3),
            "evidence": self.evidence,
            "supporting_symbols": sorted(set(self.supporting_symbols)),
            "evidence_strength": self.evidence_strength,
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
# Impact Evidence Generators
# ══════════════════════════════════════════════════════════════════════════════

def _extract_tokens(symbol: str) -> set[str]:
    """Extract meaningful tokens from a symbol name."""
    symbol_lower = symbol.lower()
    # Split on underscore, camelCase, and digits
    parts: set[str] = set()
    for part in symbol_lower.split("_"):
        if part and part not in {"self", "cls", "get", "set", "handle", "process", "_", ""}:
            parts.add(part)
    return parts


def _domain_flow_evidence(
    symbols: dict[str, str],
) -> list[ImpactEvidence]:
    """RULE 1 — Canonical flow evidence.

    For each symbol, if its name contains a domain key that maps to
    downstream domains, create weak evidence to symbols in those downstream domains.
    """
    evidence: list[ImpactEvidence] = []
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
                evidence.append(ImpactEvidence(
                    source_symbol=from_sym,
                    target_symbol=to_sym,
                    evidence_type="canonical_flow",
                    confidence=0.4,
                    explanation=f"{from_domain} → {to_domain} is canonical billing flow",
                ))

    return evidence


def _is_near_match(domain: str, downstream_keys: list[str]) -> bool:
    """Check if domain is a near-match of any downstream key."""
    domain_lower = domain.lower()
    for key in downstream_keys:
        key_lower = key.lower()
        if key_lower in domain_lower or domain_lower in key_lower:
            return True
    return False


def _symbol_token_evidence(
    symbols: dict[str, str],
) -> list[ImpactEvidence]:
    """RULE 2 — Symbol token match evidence.

    If two symbols share a meaningful token (tax, invoice, order, payment, etc.),
    create a weak connection.
    """
    evidence: list[ImpactEvidence] = []
    high_value_tokens: set[str] = {
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
                evidence.append(ImpactEvidence(
                    source_symbol=from_sym,
                    target_symbol=to_sym,
                    evidence_type="naming_similarity",
                    confidence=0.25,
                    explanation=f"shared token(s): {', '.join(sorted(shared))}",
                ))

    return evidence


def _co_location_evidence(
    symbols: dict[str, str],
) -> list[ImpactEvidence]:
    """RULE 3 — Change co-location evidence.

    If multiple modified symbols are in the same file, connect them weakly.
    """
    evidence: list[ImpactEvidence] = []

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
                evidence.append(ImpactEvidence(
                    source_symbol=from_sym,
                    target_symbol=to_sym,
                    evidence_type="shared_file",
                    confidence=0.15,
                    explanation=f"co-located in same file: {file_path}",
                ))

    return evidence


# ══════════════════════════════════════════════════════════════════════════════
# Evidence Synthesizer — clusters raw evidence into themes
# ══════════════════════════════════════════════════════════════════════════════

def _extract_theme(evidence: ImpactEvidence) -> str:
    """Extract a theme key from an evidence record.

    Groups by the domain pair (e.g., 'tax_to_invoice', 'order_to_payment').
    """
    # Extract domain tokens from source and target
    source_tokens = _extract_tokens(evidence.source_symbol)
    target_tokens = _extract_tokens(evidence.target_symbol)

    # Find the most meaningful token from each
    domain_tokens: set[str] = {"tax", "invoice", "order", "payment", "checkout",
                                "billing", "auth", "user", "fulfillment", "inventory",
                                "catalog", "notification", "cart", "discount", "coupon",
                                "subscription", "ledger", "shipping", "pricing"}

    source_domain = "general"
    for t in source_tokens:
        if t in domain_tokens:
            source_domain = t
            break

    target_domain = "general"
    for t in target_tokens:
        if t in domain_tokens:
            target_domain = t
            break

    # If same domain, use just that domain
    if source_domain == target_domain:
        return f"{source_domain}_related"

    return f"{source_domain}_to_{target_domain}"


def _generate_cluster_explanation(
    theme: str,
    sources: list[str],
    targets: list[str],
    evidence_types: list[str],
) -> str:
    """Generate a human-readable explanation for a cluster."""
    # Count unique evidence types
    type_counts: dict[str, int] = {}
    for et in evidence_types:
        type_counts[et] = type_counts.get(et, 0) + 1

    dominant_types = sorted(type_counts, key=lambda k: type_counts[k], reverse=True)[:2]

    parts = theme.split("_to_")
    if len(parts) == 2:
        src, tgt = parts
        return (
            f"{src.capitalize()}-related symbols appear connected to "
            f"{tgt.replace('_', ' ')} flows "
            f"(evidence: {', '.join(dominant_types)})"
        )
    else:
        return (
            f"Multiple {theme.replace('_', ' ')} symbols appear interconnected "
            f"(evidence: {', '.join(dominant_types)})"
        )


def synthesize_evidence(
    evidence_list: list[ImpactEvidence],
) -> list[EvidenceCluster]:
    """Cluster raw ImpactEvidence into themed EvidenceCluster objects.

    Instead of N×M individual records, group by theme so the LLM
    sees a single coherent signal per risk area.
    """
    if not evidence_list:
        return []

    # Group by theme
    clusters: dict[str, dict[str, Any]] = {}

    for ev in evidence_list:
        theme = _extract_theme(ev)

        if theme not in clusters:
            clusters[theme] = {
                "sources": set(),
                "targets": set(),
                "confidences": [],
                "evidence_types": [],
            }

        clusters[theme]["sources"].add(ev.source_symbol)
        clusters[theme]["targets"].add(ev.target_symbol)
        clusters[theme]["confidences"].append(ev.confidence)
        clusters[theme]["evidence_types"].append(ev.evidence_type)

    # Build cluster objects
    result: list[EvidenceCluster] = []
    for theme, data in clusters.items():
        avg_confidence = sum(data["confidences"]) / len(data["confidences"]) if data["confidences"] else 0.0

        # Determine evidence strength from dominant type
        type_counts: dict[str, int] = {}
        for et in data["evidence_types"]:
            type_counts[et] = type_counts.get(et, 0) + 1
        dominant_type = max(type_counts, key=lambda k: type_counts[k])
        strength = get_evidence_strength(dominant_type)

        explanation = _generate_cluster_explanation(
            theme=theme,
            sources=list(data["sources"]),
            targets=list(data["targets"]),
            evidence_types=data["evidence_types"],
        )

        result.append(EvidenceCluster(
            theme=theme,
            sources=list(data["sources"]),
            targets=list(data["targets"]),
            confidence=avg_confidence,
            explanation=explanation,
            evidence_types=list(set(data["evidence_types"])),
            evidence_strength=strength.value,
        ))

    # Sort by confidence descending
    result.sort(key=lambda c: -c.confidence)

    return result


def synthesize_evidence_summary(
    evidence_list: list[ImpactEvidence],
) -> list[EvidenceSummary]:
    """Synthesize raw evidence into EvidenceSummary objects for the LLM.

    The deterministic engine answers "what appears involved?"
    before the LLM sees anything.
    """
    clusters = synthesize_evidence(evidence_list)

    summaries: list[EvidenceSummary] = []
    for cluster in clusters:
        # Build claims from the cluster
        claims: list[str] = []
        parts = cluster.theme.split("_to_")
        if len(parts) == 2:
            src, tgt = parts
            claims.append(
                f"{src.capitalize()}-related symbols appear connected to "
                f"{tgt.replace('_', ' ')} generation."
            )
            claims.append(
                f"{tgt.capitalize()} values appear dependent on modified "
                f"{src} metadata."
            )
        else:
            claims.append(
                f"Multiple {cluster.theme.replace('_', ' ')} symbols "
                f"appear interconnected."
            )

        # Add a claim about the evidence type
        if cluster.evidence_types:
            dominant = max(set(cluster.evidence_types), key=cluster.evidence_types.count)
            if dominant == "canonical_flow":
                claims.append(
                    f"Connections follow standard domain flow patterns."
                )
            elif dominant == "naming_similarity":
                claims.append(
                    f"Symbols share naming conventions suggesting related functionality."
                )
            elif dominant == "shared_file":
                claims.append(
                    f"Symbols are co-located in the same file."
                )

        all_symbols = list(set(cluster.sources + cluster.targets))

        summaries.append(EvidenceSummary(
            risk_area=cluster.theme,
            confidence=cluster.confidence,
            evidence=claims,
            supporting_symbols=all_symbols,
            evidence_strength=cluster.evidence_strength,
        ))

    return summaries


# ══════════════════════════════════════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════════════════════════════════════

def build_impact_evidence(
    all_changed_symbols: list[dict[str, str]],
    existing_edges: set[tuple[str, str]] | None = None,
) -> list[ImpactEvidence]:
    """Build impact evidence from changed symbols.

    Args:
        all_changed_symbols: List of dicts with 'symbol' and 'file' keys.
        existing_edges: Optional set of (source, target) tuples already covered by
            the causal graph. Evidence that duplicates real edges is skipped.

    Returns:
        List of ImpactEvidence entries, sorted by confidence descending.
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

    # Collect evidence from all rules
    all_evidence: list[ImpactEvidence] = []
    dedup: dict[tuple[str, str], ImpactEvidence] = {}

    for ev_list in [
        _domain_flow_evidence(symbols),
        _symbol_token_evidence(symbols),
        _co_location_evidence(symbols),
    ]:
        for ev in ev_list:
            key = (ev.source_symbol, ev.target_symbol)

            # Skip if this edge already exists in the causal graph
            if key in existing:
                continue

            # Take max confidence for same source→target pair
            if key in dedup:
                if ev.confidence > dedup[key].confidence:
                    dedup[key] = ev
            else:
                dedup[key] = ev

    all_evidence = list(dedup.values())

    # Sort by confidence descending
    all_evidence.sort(key=lambda e: (-e.confidence, e.evidence_type))

    return all_evidence


def extract_existing_edges_from_graph(
    causal_graph: Any | None = None,
) -> set[tuple[str, str]]:
    """Extract (source, target) tuples from an existing causal graph.

    Used to prevent impact evidence from duplicating real edges.
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
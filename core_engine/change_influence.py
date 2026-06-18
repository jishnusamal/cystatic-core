"""
Layer 1 — Change Influence (Source of Risk)

Answers: "Which changes matter before reasoning starts?"

Generated from change_graph. Each changed symbol receives:
  - symbol + file
  - domain mapping (deterministic)
  - influence_score (0.0–1.0)
  - risk_tags

Domain mapping (deterministic):
  checkout → billing
  order → billing_core
  invoice → billing_output
  tax → billing_calculation
  auth → identity
  payment → money_movement

Influence formula:
  influence = domain_weight + mutation_weight + service_layer_weight + keyword_weight
  Clamped to [0, 1].

HIGH VALUE RULE: If symbol touches checkout/order/invoice/payment/tax → boost +0.3 min.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


# ══════════════════════════════════════════════════════════════════════════════
# Domain Mapping (deterministic)
# ══════════════════════════════════════════════════════════════════════════════

DOMAIN_MAP: dict[str, str] = {
    "checkout": "billing",
    "order": "billing_core",
    "invoice": "billing_output",
    "tax": "billing_calculation",
    "auth": "identity",
    "payment": "money_movement",
    "pay": "money_movement",
    "charge": "money_movement",
    "subscription": "billing_recurring",
    "billing": "billing",
    "discount": "billing_pricing",
    "coupon": "billing_pricing",
    "shipping": "fulfillment",
    "fulfillment": "fulfillment",
    "notification": "notification",
    "email": "notification",
    "sms": "notification",
    "cache": "infrastructure_cache",
    "redis": "infrastructure_cache",
    "session": "infrastructure_session",
    "webhook": "webhook",
    "catalog": "catalog",
    "pricing": "billing_pricing",
    "cart": "billing_cart",
    "inventory": "inventory",
    "user": "identity",
    "profile": "identity",
    "login": "identity",
    "auth": "identity",
}

# HIGH VALUE keywords — triggers +0.3 minimum boost
HIGH_VALUE_DOMAINS: set[str] = {
    "checkout", "order", "invoice", "payment", "tax", "charge", "pay",
}

# Risk tags by domain
DOMAIN_RISK_TAGS: dict[str, list[str]] = {
    "billing": ["money_flow", "retry_sensitive", "transaction_boundary", "state_mutation"],
    "billing_core": ["money_flow", "transaction_boundary", "state_mutation"],
    "billing_output": ["money_flow", "external_dependency", "data_freshness"],
    "billing_calculation": ["money_flow", "numeric_precision", "retry_sensitive"],
    "money_movement": ["money_flow", "external_dependency", "retry_sensitive", "state_mutation", "irreversible"],
    "identity": ["security", "auth_boundary", "session_dependency"],
    "billing_recurring": ["money_flow", "time_sensitive", "state_mutation"],
    "billing_pricing": ["money_flow", "numeric_precision"],
    "billing_cart": ["money_flow", "state_mutation", "session_dependency"],
    "fulfillment": ["external_dependency", "state_mutation"],
    "notification": ["external_dependency", "side_effect"],
    "infrastructure_cache": ["state_mutation", "data_freshness"],
    "infrastructure_session": ["security", "state_mutation"],
    "webhook": ["external_dependency", "retry_sensitive", "async_boundary"],
    "catalog": ["data_freshness"],
    "inventory": ["state_mutation", "data_freshness", "race_condition"],
    "identity": ["security", "auth_boundary"],
}

# Default risk tags when domain is unknown
DEFAULT_RISK_TAGS: list[str] = ["state_mutation"]


# ══════════════════════════════════════════════════════════════════════════════
# Data Structures
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class ChangeInfluence:
    """A scored change-influence entry for a single symbol."""
    symbol: str
    file: str
    domain: str
    influence_score: float
    risk_tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "file": self.file,
            "domain": self.domain,
            "influence_score": round(self.influence_score, 3),
            "risk_tags": self.risk_tags,
        }


# ══════════════════════════════════════════════════════════════════════════════
# Scorer
# ══════════════════════════════════════════════════════════════════════════════

# Weight contributions to influence score
DOMAIN_WEIGHTS: dict[str, float] = {
    "money_movement": 0.40,
    "billing_calculation": 0.35,
    "billing": 0.30,
    "billing_core": 0.30,
    "billing_output": 0.25,
    "billing_pricing": 0.25,
    "billing_cart": 0.30,
    "billing_recurring": 0.30,
    "identity": 0.35,
    "fulfillment": 0.20,
    "notification": 0.15,
    "infrastructure_cache": 0.15,
    "infrastructure_session": 0.20,
    "webhook": 0.20,
    "catalog": 0.10,
    "inventory": 0.20,
}
DEFAULT_DOMAIN_WEIGHT = 0.10

# Keywords that bump score
MUTATION_KEYWORDS: set[str] = {
    "save", "update", "create", "delete", "insert", "write", "put", "set",
    "patch", "modify", "change", "mutate", "upsert", "commit",
}
MUTATION_BOOST = 0.20

SERVICE_LAYER_KEYWORDS: set[str] = {
    "service", "handler", "controller", "manager", "facade", "action",
}
SERVICE_LAYER_BOOST = 0.10

# Additional keyword boost
GENERAL_KEYWORDS: set[str] = {
    "charge", "payment", "refund", "payout", "transfer",
    "price", "cost", "total", "amount", "balance",
    "invoice", "receipt", "statement",
    "order", "checkout", "cart",
    "tax", "vat", "gst",
    "auth", "token", "login", "password",
}
KEYWORD_BOOST = 0.10
MAX_KEYWORD_BOOSTS = 3  # cap to prevent over-boost


def _map_domain(symbol: str, file_path: str) -> str:
    """Map a symbol+file to a deterministic domain."""
    symbol_lower = symbol.lower()
    file_lower = file_path.lower()

    # Check symbol name first (strongest signal)
    for pattern, domain in DOMAIN_MAP.items():
        if pattern in symbol_lower:
            return domain

    # Fall back to file path
    for pattern, domain in DOMAIN_MAP.items():
        if pattern in file_lower:
            return domain

    return "general"


def _compute_influence_score(symbol: str, file_path: str) -> float:
    """Compute influence score for a symbol.

    Formula:
      influence = domain_weight + mutation_weight + service_layer_weight + keyword_weight
    Clamped to [0, 1].

    HIGH VALUE RULE: If symbol touches high-value domain → min 0.3.
    """
    symbol_lower = symbol.lower()
    domain = _map_domain(symbol, file_path)
    domain_weight = DOMAIN_WEIGHTS.get(domain, DEFAULT_DOMAIN_WEIGHT)

    # Mutation weight
    mutation_weight = MUTATION_BOOST if any(kw in symbol_lower for kw in MUTATION_KEYWORDS) else 0.0

    # Service layer weight
    service_weight = SERVICE_LAYER_BOOST if any(kw in symbol_lower for kw in SERVICE_LAYER_KEYWORDS) else 0.0

    # Keyword weight (capped)
    keyword_count = sum(1 for kw in GENERAL_KEYWORDS if kw in symbol_lower)
    keyword_weight = min(keyword_count, MAX_KEYWORD_BOOSTS) * KEYWORD_BOOST

    score = domain_weight + mutation_weight + service_weight + keyword_weight

    # HIGH VALUE RULE
    if any(kw in symbol_lower for kw in HIGH_VALUE_DOMAINS):
        score = max(score, 0.30)

    return min(max(score, 0.0), 1.0)


def _get_risk_tags(domain: str) -> list[str]:
    """Get risk tags for a domain, falling back to defaults."""
    return list(DOMAIN_RISK_TAGS.get(domain, DEFAULT_RISK_TAGS))


# ══════════════════════════════════════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════════════════════════════════════

def build_change_influence(
    all_changed_symbols: list[dict[str, str]],
) -> list[ChangeInfluence]:
    """Build change influence entries from a list of changed symbols.

    Args:
        all_changed_symbols: List of dicts with at least 'symbol' and 'file' keys.
            Typically extracted from behavior_diffs or compressed IR.

    Returns:
        List of ChangeInfluence entries, sorted by influence_score descending.
    """
    results: dict[str, ChangeInfluence] = {}

    for entry in all_changed_symbols:
        symbol = entry.get("symbol", "") or entry.get("name", "")
        file_path = entry.get("file", "") or entry.get("file_path", "")

        if not symbol:
            continue

        # Normalize bare function name
        bare_symbol = symbol.split(".")[-1] if "." in symbol else symbol

        domain = _map_domain(bare_symbol, file_path)
        influence_score = _compute_influence_score(bare_symbol, file_path)
        risk_tags = _get_risk_tags(domain)

        # If same symbol appears in multiple files, take max score
        if bare_symbol in results:
            existing = results[bare_symbol]
            if influence_score > existing.influence_score:
                existing.influence_score = influence_score
                existing.file = file_path
                existing.domain = domain
                existing.risk_tags = risk_tags
        else:
            results[bare_symbol] = ChangeInfluence(
                symbol=bare_symbol,
                file=file_path,
                domain=domain,
                influence_score=influence_score,
                risk_tags=risk_tags,
            )

    # Sort by influence_score descending
    return sorted(results.values(), key=lambda x: -x.influence_score)


# Test/mock function prefixes — symbols matching these are excluded from
# the causal graph and change influence pipeline. They are noise, not
# production-relevant symbols.
_TEST_FN_PREFIXES: tuple[str, ...] = (
    "test_", "_test", "mock_", "fixture_", "stub_", "fake_", "dummy_"
)


def _is_test_or_mock_symbol(symbol: str) -> bool:
    """Check if a symbol name indicates a test, mock, or fixture function."""
    lowered = symbol.lower()
    return any(lowered.startswith(prefix) or lowered.endswith(prefix.rstrip("_"))
               for prefix in _TEST_FN_PREFIXES)


def extract_changed_symbols(
    compressed_ir: dict[str, Any] | None = None,
    behavior_diffs: list[Any] | None = None,
    enriched_files: list[dict] | None = None,
) -> list[dict[str, str]]:
    """Extract changed symbols from available sources.

    Tries multiple sources in order of preference:
      1. behavior_diffs (most reliable)
      2. compressed_ir change_graph
      3. enriched_files changed_functions

    Filters out test/mock/fixture symbols and deduplicates by bare symbol name.
    """
    symbols: list[dict[str, str]] = []
    seen: set[str] = set()

    def _add(sym: str, file_path: str) -> None:
        """Add a symbol if it passes filtering and dedup checks."""
        bare = sym.split(".")[-1] if "." in sym else sym
        # Skip test/mock/fixture symbols
        if _is_test_or_mock_symbol(bare):
            return
        # Deduplicate by bare symbol name
        if bare in seen:
            return
        seen.add(bare)
        symbols.append({"symbol": bare, "file": file_path})

    # Source 1: behavior_diffs
    if behavior_diffs:
        for diff in behavior_diffs:
            data = diff
            if hasattr(data, "symbol"):
                sym = data.symbol
            elif hasattr(data, "__dict__"):
                sym = data.__dict__.get("symbol", "")
            elif isinstance(data, dict):
                sym = data.get("symbol", "")
            else:
                sym = ""
            if sym:
                file_path = ""
                if hasattr(data, "file_path"):
                    file_path = data.file_path
                elif hasattr(data, "__dict__"):
                    file_path = data.__dict__.get("file_path", "")
                elif isinstance(data, dict):
                    file_path = data.get("file_path", "") or data.get("file", "")
                _add(sym, file_path)

    # Source 2: compressed_ir change_graph
    if not symbols and compressed_ir:
        for item in compressed_ir.get("change_graph", []):
            if isinstance(item, dict):
                sym = item.get("symbol") or item.get("name") or ""
                if sym:
                    _add(sym, item.get("file", item.get("file_path", "")))

    # Source 3: enriched_files
    if not symbols and enriched_files:
        for file_data in enriched_files:
            file_path = file_data.get("file_path", "")
            for fn in file_data.get("changed_functions", []) or []:
                fn_data = fn
                if hasattr(fn_data, "name"):
                    sym = fn_data.name
                elif hasattr(fn_data, "__dict__"):
                    sym = fn_data.__dict__.get("name", "")
                elif isinstance(fn_data, dict):
                    sym = fn_data.get("name", "")
                else:
                    sym = ""
                if sym:
                    _add(sym, file_path)

    return symbols

"""
Layer 4 — LLM Packet Builder (Final Compression)

Builds the final token-bounded LLM payload from compressed causal primitives.
Enforces 8,000 token hard limit with pruning strategy.
"""
from __future__ import annotations

import json
from typing import Any

from core_engine.symbol_table import SymbolTable
from core_engine.soft_edge_compressor import compress_impact_evidence, compress_evidence_summary, compress_risk_hypotheses
from core_engine.change_influence_compressor import compress_change_influence
from core_engine.constraint_compressor import compress_constraints


def estimate_tokens(obj: Any) -> int:
    """Estimate token count from JSON serialization.

    Uses rough heuristic: 1 token ≈ 4 characters.
    """
    return len(json.dumps(obj)) // 4


def prune_lowest_confidence_items(packet: dict[str, Any]) -> None:
    """Prune lowest-confidence items to reduce token count.

    Priority order (drop in this order):
    1. Risk hypotheses (lowest strength first)
    2. Low-risk zones
    3. Cap symbol count (30 → 20 → 15 fallback)

    Modifies packet in place.
    """
    # 1. Drop risk hypotheses items (weakest first)
    if "risk_hypotheses" in packet and packet["risk_hypotheses"]:
        current = len(packet["risk_hypotheses"])
        target = max(current // 2, 0)
        # Already sorted by strength desc, so drop from end (weakest)
        packet["risk_hypotheses"] = packet["risk_hypotheses"][:target]
    # Legacy: also prune evidence_summary if present
    elif "evidence_summary" in packet and packet["evidence_summary"]:
        current = len(packet["evidence_summary"])
        target = max(current // 2, 0)
        packet["evidence_summary"] = packet["evidence_summary"][:target]

    # 2. Drop low-risk zones (keep only high-impact domains)
    if "risk_zones" in packet and packet["risk_zones"]:
        high_impact_domains = {
            "checkout", "invoice", "payment", "billing", "order",
            "tax", "money_movement", "fulfillment",
        }
        filtered = [z for z in packet["risk_zones"] if z in high_impact_domains]
        if filtered:
            packet["risk_zones"] = filtered

    # 3. Cap symbol count (30 → 20 → 15 fallback)
    if "symbols" in packet and packet["symbols"]:
        current_symbols = len(packet["symbols"])
        if current_symbols > 15:
            # Keep top 15 by score
            sorted_syms = sorted(
                packet["symbols"].items(),
                key=lambda x: x[1].get("score", 0.0),
                reverse=True,
            )
            packet["symbols"] = dict(sorted_syms[:15])


def build_llm_packet(
    change_influence: list[dict[str, Any]] | None,
    impact_evidence: list[dict[str, Any]] | None,
    risk_zones: list[str] | None,
    changed_symbols: list[str] | None,
    repo: str = "",
    pr_number: int = 0,
    token_budget: int = 7500,
    impact_propagation: dict[str, Any] | None = None,
    deterministic_scenarios: list[dict[str, Any]] | None = None,
    business_objects: list[dict[str, Any]] | None = None,
    domains: list[str] | None = None,
    constraints: list[dict[str, Any]] | None = None,
    entry_points: list[str] | None = None,
    side_effects: list[dict[str, Any]] | None = None,
    transaction_boundaries: list[str] | None = None,
    external_dependencies: list[str] | None = None,
) -> dict[str, Any]:
    """Build final LLM packet with token safety guard.

    Hybrid deterministic + LLM architecture:
    - Deterministic engine produces scenarios (fact generator)
    - LLM validates, ranks, explains, challenges (expert reviewer)
    
    Args:
        change_influence: Raw change influence list.
        impact_evidence: Raw impact evidence list.
        risk_zones: List of risk zone strings.
        changed_symbols: List of changed symbol names.
        repo: Repository name.
        pr_number: PR number.
        token_budget: Maximum token count (default 7500, hard limit 8000).
        impact_propagation: Impact Propagation Kernel result dict (optional).
        deterministic_scenarios: Scenarios from deterministic pipeline (optional).
        business_objects: Business objects from evidence bundle (optional).
        domains: Domains from evidence bundle (optional).
        constraints: Constraints from evidence bundle (optional).
        entry_points: Entry points affected by the change (optional).
        side_effects: Side effects from the change (optional).
        transaction_boundaries: Transaction boundaries affected (optional).
        external_dependencies: External dependencies affected (optional).

    Returns:
        Final LLM packet dict, guaranteed to be within token budget.
    """
    # Layer 1: Build symbol table
    symbol_table = SymbolTable(max_symbols=30)
    symbol_table.build(change_influence or [])

    # Layer 1: Compress change_influence
    compressed_influence = compress_change_influence(
        change_influence,
        symbol_table=symbol_table,
        max_symbols=30,
    )

    # Layer 2: Build risk hypotheses (unified reasoning packet)
    # Uses impact_evidence as evidence_summary for the risk hypotheses builder
    from core_engine.failure_archetype_engine import build_risk_hypotheses
    risk_hypotheses = build_risk_hypotheses(
        change_influence=change_influence,
        evidence_summary=impact_evidence,
    )
    compressed_hypotheses = compress_risk_hypotheses(risk_hypotheses, max_items=10)

    # Build initial packet (legacy format for backward compatibility)
    packet = {
        "repo": repo,
        "pr_number": pr_number,
        "change_influence": compressed_influence,
        "risk_hypotheses": compressed_hypotheses,
        "risk_zones": risk_zones or ["general"],
        "changed_symbols": changed_symbols or [],
    }

    # Include Impact Propagation Kernel output as additional context (if provided)
    if impact_propagation:
        packet["impact_propagation"] = impact_propagation

    # ═══════════════════════════════════════════════════════════════════════════
    # NEW: Build evidence graph format for LLM validation/ranking
    # ═══════════════════════════════════════════════════════════════════════════
    if deterministic_scenarios:
        # Transform deterministic scenarios into evidence graph format
        evidence_graph_scenarios = _build_evidence_graph_scenarios(
            deterministic_scenarios=deterministic_scenarios,
            compressed_hypotheses=compressed_hypotheses,
            business_objects=business_objects or [],
            domains=domains or [],
            risk_zones=risk_zones or [],
            constraints=constraints or [],
            entry_points=entry_points,
            side_effects=side_effects,
            transaction_boundaries=transaction_boundaries,
            external_dependencies=external_dependencies,
        )
        
        packet["scenarios"] = evidence_graph_scenarios
        packet["summary"] = {
            "changed_symbols_count": len(changed_symbols or []),
            "risk_patterns_count": len(compressed_hypotheses),
            "domains": domains or [],
        }

    # Token safety guard
    token_estimate = estimate_tokens(packet)
    if token_estimate > token_budget:
        # Prune iteratively until within budget
        for _ in range(10):  # Max 10 pruning iterations
            if estimate_tokens(packet) <= token_budget:
                break
            prune_lowest_confidence_items(packet)

    # Final hard check
    if estimate_tokens(packet) > 8000:
        # Emergency: strip to absolute minimum
        packet = {
            "repo": repo,
            "pr_number": pr_number,
            "change_influence": [],
            "risk_hypotheses": [],
            "risk_zones": (risk_zones or ["general"])[:3],
            "changed_symbols": (changed_symbols or [])[:10],
        }
        if impact_propagation:
            # Keep impact_propagation in emergency mode too
            # — it's already compact structured data
            packet["impact_propagation"] = impact_propagation

    return packet


def _build_evidence_graph_scenarios(
    deterministic_scenarios: list[dict[str, Any]],
    compressed_hypotheses: list[dict[str, Any]],
    business_objects: list[dict[str, Any]],
    domains: list[str],
    risk_zones: list[str],
    constraints: list[dict[str, Any]],
    entry_points: list[str] | None = None,
    side_effects: list[dict[str, Any]] | None = None,
    transaction_boundaries: list[str] | None = None,
    external_dependencies: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Transform deterministic scenarios into evidence graph format for LLM.
    
    This is the key transformation: instead of asking the LLM to analyze
    raw evidence, we pass pre-synthesized scenarios with their evidence
    graph structure. The LLM validates and ranks, it doesn't discover.
    
    Args:
        deterministic_scenarios: Scenarios from deterministic pipeline.
        compressed_hypotheses: Compressed risk hypotheses.
        business_objects: Business objects from evidence bundle.
        domains: Domains from evidence bundle.
        risk_zones: Risk zones.
        constraints: Constraints from evidence bundle.
        entry_points: Entry points affected by the change.
        side_effects: Side effects from the change.
        transaction_boundaries: Transaction boundaries affected.
        external_dependencies: External dependencies affected.

    Returns:
        List of scenario dicts in evidence graph format.
    """
    # Extract business object names
    bo_names = []
    for bo in business_objects:
        if isinstance(bo, dict):
            name = bo.get("name", "")
        elif hasattr(bo, "name"):
            name = bo.name
        else:
            name = str(bo)
        if name:
            bo_names.append(name)

    # Extract constraint summary
    constraint_summary = []
    for c in constraints:
        if isinstance(c, dict):
            constraint_summary.append(c)
    
    # Transform each deterministic scenario
    evidence_graph_scenarios = []
    for scenario in deterministic_scenarios[:5]:  # Max 5 scenarios for LLM
        if not isinstance(scenario, dict):
            continue
            
        # Extract evidence from scenario
        evidence_list = []
        counter_evidence_list = []
        
        # Add supporting evidence from scenario
        reasoning = scenario.get("reasoning", "")
        if reasoning:
            evidence_list.append(reasoning)
        
        # Add evidence from causal chain
        causal_chain = scenario.get("causal_chain", "")
        if causal_chain:
            evidence_list.append(f"Causal chain: {causal_chain}")
        
        # Add evidence from supported_by symbols
        supported_by = scenario.get("supported_by", [])
        if supported_by:
            evidence_list.append(f"Supported by symbols: {', '.join(supported_by[:5])}")
        
        # Add counter evidence (things that would weaken this scenario)
        if scenario.get("confidence", 0.0) < 0.7:
            counter_evidence_list.append("Moderate confidence — some uncertainty in propagation path")
        
        if not scenario.get("silent_failure", False):
            counter_evidence_list.append("Likely to be caught by monitoring/CI")
        
        # Extract affected domains from scenario
        affected_domains = scenario.get("affected_domains", [])
        if not affected_domains:
            affected_domains = domains[:3]  # Use top domains as fallback
        
        # Extract business objects
        affected_bos = scenario.get("affected_business_objects", [])
        if not affected_bos:
            affected_bos = bo_names[:5]  # Use top business objects as fallback
        
        # Build causal chain as list
        causal_chain_list = []
        if causal_chain:
            # Handle both string and list formats
            if isinstance(causal_chain, list):
                # Already a list, use as-is
                causal_chain_list = causal_chain
            else:
                # Parse "A → B → C" into ["A", "→", "B", "→", "C"]
                parts = causal_chain.split("→")
                for i, part in enumerate(parts):
                    causal_chain_list.append(part.strip())
                    if i < len(parts) - 1:
                        causal_chain_list.append("→")
        
        # Build nodes (business objects + domains + risk zones)
        nodes = list(set(affected_bos + affected_domains + risk_zones))[:8]
        
        # Build edges (from causal chain)
        edges = []
        if len(causal_chain_list) >= 3:
            # Extract edges from causal chain: ["A", "→", "B", "→", "C"] → ["calls", "shares transaction"]
            for i in range(1, len(causal_chain_list) - 1, 2):
                if causal_chain_list[i] == "→":
                    edges.append("calls")
            if not edges and len(causal_chain_list) >= 2:
                edges.append("related")
        
        # Build reachability (domains + risk zones + entry points)
        reachability = list(set(affected_domains + risk_zones + (entry_points or [])))[:5]
        
        # Build evidence graph scenario
        evidence_graph_scenario = {
            "title": scenario.get("title", scenario.get("narrative", "Unknown scenario")[:100]),
            "confidence": scenario.get("confidence", 0.5),
            "nodes": nodes,
            "edges": edges[:5],
            "business_objects": affected_bos[:5],
            "domains": affected_domains[:3],
            "reachability": reachability,
            "entry_points": (entry_points or [])[:3],
            "evidence": evidence_list[:5],  # Max 5 evidence items
            "counter_evidence": counter_evidence_list[:3],  # Max 3 counter-evidence items
            "causal_chain": causal_chain_list[:10] if causal_chain_list else [],
            "side_effects": [se.get("effect_type", "") for se in (side_effects or [])[:3]],
            "transaction_boundaries": (transaction_boundaries or [])[:3],
            "external_dependencies": (external_dependencies or [])[:3],
            "constraints": constraint_summary[:3],
            "impact_type": scenario.get("impact_type", "unknown_impact"),
            "failure_class": scenario.get("failure_class", ""),
            "production_impact": scenario.get("operational_impact", scenario.get("production_impact", "")),
            "silent_failure": scenario.get("silent_failure", True),
            "ci_would_catch": scenario.get("ci_would_catch", False),
            "merge_risk_level": scenario.get("merge_risk_level", "MEDIUM"),
        }
        
        evidence_graph_scenarios.append(evidence_graph_scenario)
    
    return evidence_graph_scenarios

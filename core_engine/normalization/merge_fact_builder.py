"""
Merge Fact Builder — generates objective merge facts.

This module creates objective merge facts from deterministic analysis,
focusing on validation requirements, coverage gaps, and risk indicators.
"""
from __future__ import annotations

from typing import Any

from core_engine.models.normalized_facts import MergeFact
from core_engine.models.evidence_bundle import EvidenceBundle


class MergeFactBuilder:
    """Generates objective merge facts from deterministic analysis.
    
    Merge facts are objective statements about what the merge requires,
    not subjective assessments of whether it should proceed.
    """
    
    @staticmethod
    def build(
        bundle: EvidenceBundle,
        validation_gaps: list[Any],  # list[ValidationGap]
        canonical_risks: list[Any],  # list[CanonicalRisk]
        scenarios: list[dict[str, Any]],
    ) -> list[MergeFact]:
        """Build merge facts from analysis results.
        
        Args:
            bundle: EvidenceBundle from EvidencePipeline.
            validation_gaps: Identified validation gaps.
            canonical_risks: Canonical risk representations.
            scenarios: Failure scenarios from inference.
            
        Returns:
            List of MergeFact objects.
        """
        facts: list[MergeFact] = []
        
        # Generate facts from validation gaps
        facts.extend(MergeFactBuilder._facts_from_validation_gaps(validation_gaps))
        
        # Generate facts from risk indicators
        facts.extend(MergeFactBuilder._facts_from_risks(canonical_risks, bundle))
        
        # Generate facts from scenario coverage
        facts.extend(MergeFactBuilder._facts_from_scenarios(scenarios))
        
        # Generate facts from critical paths
        facts.extend(MergeFactBuilder._facts_from_critical_paths(bundle))
        
        # Deduplicate and limit
        facts = MergeFactBuilder._deduplicate_facts(facts)
        
        return facts[:6]  # Limit to top 6 facts
    
    @staticmethod
    def _facts_from_validation_gaps(
        validation_gaps: list[Any],
    ) -> list[MergeFact]:
        """Generate merge facts from validation gaps."""
        facts: list[MergeFact] = []
        
        if not validation_gaps:
            return facts
        
        # High-confidence gaps indicate required validation
        high_conf_gaps = [g for g in validation_gaps if g.confidence >= 0.7]
        
        if high_conf_gaps:
            gap_count = len(high_conf_gaps)
            facts.append(MergeFact(
                fact=f"Merge requires {gap_count} integration validation{'s' if gap_count > 1 else ''}.",
                category="validation",
                supporting_evidence=[g.description for g in high_conf_gaps[:2]],
                confidence=0.9,
            ))
        
        # Check for cross-domain gaps
        cross_domain_gaps = [
            g for g in validation_gaps
            if "cross-domain" in g.description.lower() or "cross domain" in g.description.lower()
        ]
        
        if cross_domain_gaps:
            facts.append(MergeFact(
                fact="Merge touches cross-domain execution paths requiring integration tests.",
                category="coverage",
                supporting_evidence=[g.description for g in cross_domain_gaps[:2]],
                confidence=0.85,
            ))
        
        return facts
    
    @staticmethod
    def _facts_from_risks(
        canonical_risks: list[Any],
        bundle: EvidenceBundle,
    ) -> list[MergeFact]:
        """Generate merge facts from risk indicators."""
        facts: list[MergeFact] = []
        
        if not canonical_risks:
            return facts
        
        # High-confidence risks
        high_conf_risks = [r for r in canonical_risks if r.confidence >= 0.8]
        
        if high_conf_risks:
            risk_count = len(high_conf_risks)
            facts.append(MergeFact(
                fact=f"Change introduces {risk_count} high-confidence risk{'s' if risk_count > 1 else ''}.",
                category="risk",
                supporting_evidence=[r.title for r in high_conf_risks[:2]],
                confidence=0.9,
            ))
        
        # Check for payment/transaction risks
        payment_risks = [
            r for r in canonical_risks
            if any(keyword in r.title.lower() for keyword in ["payment", "transaction", "checkout", "invoice"])
        ]
        
        if payment_risks:
            facts.append(MergeFact(
                fact="Change affects payment or transaction processing path.",
                category="risk",
                supporting_evidence=[r.title for r in payment_risks[:2]],
                confidence=0.85,
            ))
        
        # Check for risks touching critical domains
        critical_domain_risks = [
            r for r in canonical_risks
            if any(domain in r.affected_domains for domain in ["payment", "billing", "checkout", "order"])
        ]
        
        if critical_domain_risks:
            facts.append(MergeFact(
                fact="Change impacts critical production domains.",
                category="risk",
                supporting_evidence=[r.title for r in critical_domain_risks[:2]],
                confidence=0.8,
            ))
        
        return facts
    
    @staticmethod
    def _facts_from_scenarios(scenarios: list[dict[str, Any]]) -> list[MergeFact]:
        """Generate merge facts from scenario coverage."""
        facts: list[MergeFact] = []
        
        if not scenarios:
            return facts
        
        # Count scenarios without CI coverage
        uncovered_scenarios = [s for s in scenarios if not s.get("ci_would_catch", False)]
        
        if uncovered_scenarios:
            scenario_count = len(uncovered_scenarios)
            facts.append(MergeFact(
                fact=f"{scenario_count} failure scenario{'s' if scenario_count > 1 else ''} lack CI coverage.",
                category="coverage",
                supporting_evidence=[s.get("title", "Unknown") for s in uncovered_scenarios[:2]],
                confidence=0.85,
            ))
        
        # Check for high-confidence scenarios
        high_conf_scenarios = [s for s in scenarios if s.get("confidence", 0) >= 0.8]
        
        if high_conf_scenarios:
            facts.append(MergeFact(
                fact="High-confidence failure scenarios identified.",
                category="risk",
                supporting_evidence=[s.get("title", "Unknown") for s in high_conf_scenarios[:2]],
                confidence=0.9,
            ))
        
        return facts
    
    @staticmethod
    def _facts_from_critical_paths(bundle: EvidenceBundle) -> list[MergeFact]:
        """Generate merge facts from critical execution paths."""
        facts: list[MergeFact] = []
        
        # Check for payment/transaction paths
        payment_symbols = [
            cs.symbol for cs in bundle.changed_symbols
            if any(keyword in cs.symbol.lower() for keyword in ["payment", "transaction", "checkout", "invoice", "order"])
        ]
        
        if payment_symbols:
            facts.append(MergeFact(
                fact="Change touches payment or order processing path.",
                category="risk",
                supporting_evidence=payment_symbols[:3],
                confidence=0.8,
            ))
        
        # Check for cross-domain evidence
        cross_domain_count = sum(
            1 for ev in bundle.impact_evidence
            if ev.evidence_type and "cross" in ev.evidence_type.lower()
        )
        
        if cross_domain_count > 0:
            facts.append(MergeFact(
                fact=f"Change creates {cross_domain_count} cross-domain connection{'s' if cross_domain_count > 1 else ''}.",
                category="architecture",
                supporting_evidence=[f"{cross_domain_count} cross-domain evidence items"],
                confidence=0.75,
            ))
        
        # Check for risk anchors
        if bundle.risk_anchors:
            anchor_count = len(bundle.risk_anchors)
            facts.append(MergeFact(
                fact=f"Change introduces {anchor_count} risk anchor{'s' if anchor_count > 1 else ''}.",
                category="risk",
                supporting_evidence=[ra.symbol for ra in bundle.risk_anchors[:3] if hasattr(ra, "symbol")],
                confidence=0.85,
            ))
        
        return facts
    
    @staticmethod
    def _deduplicate_facts(facts: list[MergeFact]) -> list[MergeFact]:
        """Remove duplicate facts based on category and similarity."""
        seen_categories: set[str] = set()
        deduplicated: list[MergeFact] = []
        
        for fact in facts:
            # Use category as deduplication key
            if fact.category not in seen_categories:
                seen_categories.add(fact.category)
                deduplicated.append(fact)
        
        return deduplicated
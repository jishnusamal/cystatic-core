"""
Risk Canonicalizer — merges duplicate hypotheses into canonical risks.

This module consolidates similar hypotheses and impact evidence into
canonical risk representations.
"""
from __future__ import annotations

from typing import Any

from core_engine.models.normalized_facts import CanonicalRisk
from core_engine.models.evidence_bundle import EvidenceBundle


class RiskCanonicalizer:
    """Merges duplicate hypotheses into canonical risks.
    
    This canonicalizer identifies related hypotheses and impact evidence
    and consolidates them into canonical risk representations.
    """
    
    @staticmethod
    def canonicalize(
        bundle: EvidenceBundle,
        hypotheses: list[dict[str, Any]],
    ) -> list[CanonicalRisk]:
        """Canonicalize risks from hypotheses and evidence.
        
        Args:
            bundle: EvidenceBundle from EvidencePipeline.
            hypotheses: Generated impact hypotheses.
            
        Returns:
            List of CanonicalRisk objects.
        """
        risks: list[CanonicalRisk] = []
        
        # Group hypotheses by domain/symbol patterns
        risk_groups = RiskCanonicalizer._group_related_hypotheses(hypotheses)
        
        # Convert each group to a canonical risk
        for group in risk_groups[:5]:  # Limit to top 5 risks
            canonical_risk = RiskCanonicalizer._build_canonical_risk(group, bundle)
            if canonical_risk:
                risks.append(canonical_risk)
        
        # Also extract risks from high-confidence impact evidence
        risks.extend(RiskCanonicalizer._extract_evidence_risks(bundle))
        
        # Deduplicate and limit
        risks = RiskCanonicalizer._deduplicate_risks(risks)
        
        return risks[:5]  # Limit to top 5 risks
    
    @staticmethod
    def _group_related_hypotheses(
        hypotheses: list[dict[str, Any]],
    ) -> list[list[dict[str, Any]]]:
        """Group related hypotheses together.
        
        Hypotheses are related if they share:
        - Same domain
        - Related symbols
        - Similar impact types
        """
        groups: list[list[dict[str, Any]]] = []
        assigned: set[int] = set()
        
        for i, hyp in enumerate(hypotheses):
            if i in assigned:
                continue
            
            group = [hyp]
            assigned.add(i)
            
            hyp_domains = set(hyp.get("affected_domains", []))
            hyp_symbols = set([hyp.get("source_symbol", ""), hyp.get("target_symbol", "")])
            hyp_symbols.discard("")
            
            for j, other_hyp in enumerate(hypotheses[i+1:], start=i+1):
                if j in assigned:
                    continue
                
                other_domains = set(other_hyp.get("affected_domains", []))
                other_symbols = set([other_hyp.get("source_symbol", ""), other_hyp.get("target_symbol", "")])
                other_symbols.discard("")
                
                # Check if related
                shared_domains = hyp_domains & other_domains
                shared_symbols = hyp_symbols & other_symbols
                
                if shared_domains or shared_symbols:
                    group.append(other_hyp)
                    assigned.add(j)
            
            if group:
                groups.append(group)
        
        return groups
    
    @staticmethod
    def _build_canonical_risk(
        group: list[dict[str, Any]],
        bundle: EvidenceBundle,
    ) -> CanonicalRisk | None:
        """Build a canonical risk from a group of related hypotheses."""
        if not group:
            return None
        
        # Use the highest-confidence hypothesis as the base
        base_hyp = max(group, key=lambda h: h.get("confidence", 0))
        
        # Collect all affected symbols and domains
        all_symbols: set[str] = set()
        all_domains: set[str] = set()
        all_evidence: list[str] = []
        
        for hyp in group:
            all_symbols.add(hyp.get("source_symbol", ""))
            all_symbols.add(hyp.get("target_symbol", ""))
            all_domains.update(hyp.get("affected_domains", []))
            
            if hyp.get("evidence_summary"):
                all_evidence.append(hyp["evidence_summary"])
        
        all_symbols.discard("")
        
        # Build title from the base hypothesis
        title = base_hyp.get("hypothesis", "Unknown risk")[:100]
        
        # Build description
        if len(group) > 1:
            description = f"Multiple related risks identified: {', '.join([h.get('hypothesis', '')[:50] for h in group[:3]])}"
        else:
            description = base_hyp.get("description", base_hyp.get("hypothesis", ""))
        
        # Extract production invariant if mentioned
        production_invariant = RiskCanonicalizer._extract_production_invariant(base_hyp)
        
        # Calculate average confidence
        avg_confidence = sum(h.get("confidence", 0.5) for h in group) / len(group)
        
        return CanonicalRisk(
            title=title,
            affected_symbols=list(all_symbols)[:5],
            affected_domains=list(all_domains)[:5],
            production_invariant=production_invariant,
            confidence=round(avg_confidence, 2),
            supporting_evidence=all_evidence[:3],
        )
    
    @staticmethod
    def _extract_production_invariant(hypothesis: dict[str, Any]) -> str:
        """Extract production invariant from hypothesis."""
        hyp_text = hypothesis.get("hypothesis", "").lower()
        
        # Look for invariant patterns
        if "must" in hyp_text or "should" in hyp_text:
            return hypothesis.get("hypothesis", "")[:200]
        
        # Look for constraint patterns
        if "always" in hyp_text or "never" in hyp_text:
            return hypothesis.get("hypothesis", "")[:200]
        
        return ""
    
    @staticmethod
    def _extract_evidence_risks(bundle: EvidenceBundle) -> list[CanonicalRisk]:
        """Extract risks from high-confidence impact evidence."""
        risks: list[CanonicalRisk] = []
        
        # Get high-confidence evidence
        high_conf_evidence = [
            ev for ev in bundle.impact_evidence
            if ev.confidence >= 0.8
        ]
        
        # Group by evidence type
        for ev in high_conf_evidence[:3]:  # Limit to top 3
            try:
                source = ev.source.name if hasattr(ev.source, "name") else str(ev.source)
                target = ev.target.name if hasattr(ev.target, "name") else str(ev.target)
                evidence_type = ev.evidence_type.value if hasattr(ev.evidence_type, "value") else str(ev.evidence_type)
                
                # Find affected domains
                domains: set[str] = set()
                for ev2 in bundle.impact_evidence:
                    try:
                        s = ev2.source.name if hasattr(ev2.source, "name") else ""
                        t = ev2.target.name if hasattr(ev2.target, "name") else ""
                        if source in s or source in t or target in s or target in t:
                            if ev2.evidence_type and "domain" in ev2.evidence_type.lower():
                                domains.add(s)
                                domains.add(t)
                    except Exception:
                        continue
                
                risks.append(CanonicalRisk(
                    title=f"{source} → {target} coupling",
                    affected_symbols=[source, target],
                    affected_domains=list(domains)[:3],
                    production_invariant="",
                    confidence=ev.confidence,
                    supporting_evidence=[ev.explanation] if ev.explanation else [],
                ))
            except Exception:
                continue
        
        return risks
    
    @staticmethod
    def _deduplicate_risks(risks: list[CanonicalRisk]) -> list[CanonicalRisk]:
        """Remove duplicate risks based on affected symbols."""
        seen_symbol_sets: set[str] = set()
        deduplicated: list[CanonicalRisk] = []
        
        for risk in risks:
            # Create a key from sorted symbols
            symbol_key = ",".join(sorted(risk.affected_symbols))
            
            if symbol_key not in seen_symbol_sets:
                seen_symbol_sets.add(symbol_key)
                deduplicated.append(risk)
        
        return deduplicated
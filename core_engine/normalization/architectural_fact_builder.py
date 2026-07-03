"""
Architectural Fact Builder — extracts stable architectural observations.

This module converts internal evidence into deterministic architectural facts
that describe the system structure and relationships.
"""
from __future__ import annotations

from typing import Any

from core_engine.models.normalized_facts import ArchitecturalFact
from core_engine.models.evidence_bundle import EvidenceBundle
from core_engine.models.impact_hypothesis import ImpactHypothesis


class ArchitecturalFactBuilder:
    """Extracts architectural facts from inference results.
    
    This builder identifies stable architectural observations from
    evidence clusters, hypotheses, and impact evidence.
    """
    
    @staticmethod
    def build(
        bundle: EvidenceBundle,
        hypotheses: list[dict[str, Any]],
        evidence_clusters: list[dict[str, Any]],
    ) -> list[ArchitecturalFact]:
        """Build architectural facts from inference results.
        
        Args:
            bundle: EvidenceBundle from EvidencePipeline.
            hypotheses: Generated impact hypotheses.
            evidence_clusters: Aggregated evidence clusters.
            
        Returns:
            List of ArchitecturalFact objects.
        """
        facts: list[ArchitecturalFact] = []
        
        # Extract facts from cross-domain evidence
        facts.extend(ArchitecturalFactBuilder._extract_cross_domain_facts(bundle))
        
        # Extract facts from shared execution paths
        facts.extend(ArchitecturalFactBuilder._extract_shared_path_facts(bundle, hypotheses))
        
        # Extract facts from business object dependencies
        facts.extend(ArchitecturalFactBuilder._extract_business_object_facts(bundle))
        
        # Deduplicate and limit
        facts = ArchitecturalFactBuilder._deduplicate_facts(facts)
        
        return facts[:10]  # Limit to top 10 facts
    
    @staticmethod
    def _extract_cross_domain_facts(bundle: EvidenceBundle) -> list[ArchitecturalFact]:
        """Extract facts from cross-domain evidence."""
        facts: list[ArchitecturalFact] = []
        
        cross_domain_evidence = [
            ev for ev in bundle.impact_evidence
            if ev.evidence_type and "cross" in ev.evidence_type.lower()
        ]
        
        # Group by source-target pairs
        seen_pairs: set[str] = set()
        for ev in cross_domain_evidence[:5]:  # Limit to top 5
            try:
                source = ev.source.name if hasattr(ev.source, "name") else str(ev.source)
                target = ev.target.name if hasattr(ev.target, "name") else str(ev.target)
                
                pair_key = f"{source}->{target}"
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)
                
                # Find affected domains
                domains = ArchitecturalFactBuilder._domains_for_symbols([source, target], bundle)
                
                facts.append(ArchitecturalFact(
                    title=f"{source} connects to {target}",
                    description=f"{source} and {target} share a cross-domain execution path",
                    symbols=[source, target],
                    domains=domains,
                    confidence=ev.confidence,
                    supporting_evidence=[ev.explanation] if ev.explanation else [],
                ))
            except Exception:
                continue
        
        return facts
    
    @staticmethod
    def _extract_shared_path_facts(
        bundle: EvidenceBundle,
        hypotheses: list[dict[str, Any]],
    ) -> list[ArchitecturalFact]:
        """Extract facts about shared execution paths."""
        facts: list[ArchitecturalFact] = []
        
        # Look for hypotheses that mention shared paths
        for hyp in hypotheses[:3]:  # Limit to top 3
            try:
                hypothesis_text = hyp.get("hypothesis", "")
                if not hypothesis_text:
                    continue
                
                # Check if hypothesis describes shared execution
                if any(keyword in hypothesis_text.lower() for keyword in [
                    "share", "common", "same path", "shared", "both"
                ]):
                    source = hyp.get("source_symbol", "")
                    target = hyp.get("target_symbol", "")
                    
                    if source and target:
                        domains = ArchitecturalFactBuilder._domains_for_symbols(
                            [source, target], bundle
                        )
                        
                        facts.append(ArchitecturalFact(
                            title=f"{source} and {target} share execution path",
                            description=hypothesis_text[:200],
                            symbols=[source, target],
                            domains=domains,
                            confidence=hyp.get("confidence", 0.5),
                            supporting_evidence=[hyp.get("evidence_summary", "")],
                        ))
            except Exception:
                continue
        
        return facts
    
    @staticmethod
    def _extract_business_object_facts(bundle: EvidenceBundle) -> list[ArchitecturalFact]:
        """Extract facts about business object dependencies."""
        facts: list[ArchitecturalFact] = []
        
        # Group evidence by business objects
        bo_evidence: dict[str, list[Any]] = {}
        for ev in bundle.impact_evidence:
            try:
                for bo in bundle.business_objects:
                    if bo.name and hasattr(ev, "source") and hasattr(ev, "target"):
                        source_name = ev.source.name if hasattr(ev.source, "name") else ""
                        target_name = ev.target.name if hasattr(ev.target, "name") else ""
                        
                        if bo.name.lower() in source_name.lower() or bo.name.lower() in target_name.lower():
                            if bo.name not in bo_evidence:
                                bo_evidence[bo.name] = []
                            bo_evidence[bo.name].append(ev)
            except Exception:
                continue
        
        # Create facts for business objects with multiple connections
        for bo_name, evidence_list in list(bo_evidence.items())[:3]:  # Limit to top 3
            if len(evidence_list) >= 2:
                connected_symbols = set()
                for ev in evidence_list:
                    try:
                        source = ev.source.name if hasattr(ev.source, "name") else ""
                        target = ev.target.name if hasattr(ev.target, "name") else ""
                        if source:
                            connected_symbols.add(source)
                        if target:
                            connected_symbols.add(target)
                    except Exception:
                        continue
                
                if len(connected_symbols) >= 2:
                    facts.append(ArchitecturalFact(
                        title=f"{bo_name} depends on multiple components",
                        description=f"{bo_name} logic depends on {', '.join(list(connected_symbols)[:3])}",
                        symbols=list(connected_symbols)[:5],
                        domains=bundle.domains[:3] if bundle.domains else [],
                        confidence=0.7,
                        supporting_evidence=[f"{len(evidence_list)} evidence items"],
                    ))
        
        return facts
    
    @staticmethod
    def _domains_for_symbols(symbols: list[str], bundle: EvidenceBundle) -> list[str]:
        """Find domains associated with given symbols."""
        domains: set[str] = set()
        for ev in bundle.impact_evidence:
            try:
                source_name = ev.source.name if hasattr(ev.source, "name") else ""
                target_name = ev.target.name if hasattr(ev.target, "name") else ""
                
                if any(sym in source_name or sym in target_name for sym in symbols):
                    if ev.evidence_type and "domain" in ev.evidence_type.lower():
                        domains.add(source_name)
                        domains.add(target_name)
            except Exception:
                continue
        
        # Fall back to bundle domains
        if not domains and bundle.domains:
            domains.update(bundle.domains[:3])
        
        return list(domains)[:5]
    
    @staticmethod
    def _deduplicate_facts(facts: list[ArchitecturalFact]) -> list[ArchitecturalFact]:
        """Remove duplicate facts based on title."""
        seen_titles: set[str] = set()
        deduplicated: list[ArchitecturalFact] = []
        
        for fact in facts:
            if fact.title not in seen_titles:
                seen_titles.add(fact.title)
                deduplicated.append(fact)
        
        return deduplicated
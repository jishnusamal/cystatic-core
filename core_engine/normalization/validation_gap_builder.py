"""
Validation Gap Builder — identifies gaps in test coverage.

This module combines production invariants with existing validation
to identify missing test coverage.
"""
from __future__ import annotations

from typing import Any

from core_engine.models.normalized_facts import ValidationGap, ProductionInvariant
from core_engine.models.evidence_bundle import EvidenceBundle


class ValidationGapBuilder:
    """Identifies validation gaps by comparing invariants to existing tests.
    
    This builder determines what validation is missing by comparing
    production invariants against existing test coverage.
    """
    
    @staticmethod
    def build(
        bundle: EvidenceBundle,
        invariants: list[ProductionInvariant],
    ) -> list[ValidationGap]:
        """Build validation gaps from invariants and evidence.
        
        Args:
            bundle: EvidenceBundle from EvidencePipeline.
            invariants: Production invariants.
            
        Returns:
            List of ValidationGap objects.
        """
        gaps: list[ValidationGap] = []
        
        # Extract existing validation from bundle
        existing_validation = ValidationGapBuilder._extract_existing_validation(bundle)
        
        # Compare each invariant against existing validation
        for invariant in invariants[:6]:  # Limit to top 6
            gap = ValidationGapBuilder._check_invariant_coverage(
                invariant, existing_validation, bundle
            )
            if gap:
                gaps.append(gap)
        
        # Also extract gaps from cross-domain evidence
        gaps.extend(ValidationGapBuilder._extract_cross_domain_gaps(bundle))
        
        # Deduplicate and limit
        gaps = ValidationGapBuilder._deduplicate_gaps(gaps)
        
        return gaps[:6]  # Limit to top 6 gaps
    
    @staticmethod
    def _extract_existing_validation(bundle: EvidenceBundle) -> dict[str, list[str]]:
        """Extract existing validation coverage from bundle."""
        validation_map: dict[str, list[str]] = {
            "domains": [],
            "symbols": [],
            "business_objects": [],
        }
        
        # Extract from constraints (which often represent validation rules)
        for constraint in bundle.constraints:
            try:
                symbol = constraint.symbol if hasattr(constraint, "symbol") else ""
                if symbol:
                    validation_map["symbols"].append(symbol)
            except Exception:
                continue
        
        # Extract from business objects
        for bo in bundle.business_objects:
            if bo.name:
                validation_map["business_objects"].append(bo.name)
        
        # Extract from domains
        validation_map["domains"] = bundle.domains[:5] if bundle.domains else []
        
        return validation_map
    
    @staticmethod
    def _check_invariant_coverage(
        invariant: ProductionInvariant,
        existing_validation: dict[str, list[str]],
        bundle: EvidenceBundle,
    ) -> ValidationGap | None:
        """Check if an invariant has sufficient validation coverage."""
        # Check if invariant symbols have validation
        invariant_symbols = set(invariant.symbols)
        validated_symbols = set(existing_validation.get("symbols", []))
        
        # Check if invariant business objects have validation
        invariant_bos = set(invariant.business_objects)
        validated_bos = set(existing_validation.get("business_objects", []))
        
        # Determine if there's a gap
        missing_symbols = invariant_symbols - validated_symbols
        missing_bos = invariant_bos - validated_bos
        
        # If critical symbols or business objects lack validation, there's a gap
        if missing_symbols or missing_bos:
            # Build description
            description_parts = []
            if missing_symbols:
                description_parts.append(f"Missing validation for symbols: {', '.join(list(missing_symbols)[:3])}")
            if missing_bos:
                description_parts.append(f"Missing validation for business objects: {', '.join(list(missing_bos)[:3])}")
            
            description = ". ".join(description_parts)
            
            # Determine what validation exists
            existing_parts = []
            if invariant_symbols & validated_symbols:
                existing_parts.append(f"Unit tests exist for {', '.join(list(invariant_symbols & validated_symbols)[:2])}")
            if invariant_bos & validated_bos:
                existing_parts.append(f"Business object tests exist for {', '.join(list(invariant_bos & validated_bos)[:2])}")
            
            existing_validation_desc = ". ".join(existing_parts) if existing_parts else "Limited validation coverage detected"
            
            # Determine what validation is missing
            missing_validation = ValidationGapBuilder._recommend_missing_validation(
                invariant, missing_symbols, missing_bos
            )
            
            return ValidationGap(
                description=description,
                invariant=invariant.statement,
                existing_validation=existing_validation_desc,
                missing_validation=missing_validation,
                affected_symbols=list(invariant_symbols)[:5],
                affected_domains=invariant.domains[:3],
                confidence=invariant.confidence,
            )
        
        return None
    
    @staticmethod
    def _recommend_missing_validation(
        invariant: ProductionInvariant,
        missing_symbols: set[str],
        missing_bos: set[str],
    ) -> str:
        """Recommend what validation is missing."""
        recommendations = []
        
        if missing_symbols:
            symbol = list(missing_symbols)[0]
            recommendations.append(f"Integration test covering {symbol} execution path")
        
        if missing_bos:
            bo = list(missing_bos)[0]
            recommendations.append(f"End-to-end test for {bo} workflow")
        
        # Check invariant statement for clues
        invariant_lower = invariant.statement.lower()
        if "payment" in invariant_lower or "transaction" in invariant_lower:
            recommendations.append("Payment flow integration test")
        if "order" in invariant_lower:
            recommendations.append("Order state transition test")
        if "discount" in invariant_lower:
            recommendations.append("Discount application and expiration test")
        
        return "; ".join(recommendations[:2]) if recommendations else "Comprehensive integration test"
    
    @staticmethod
    def _extract_cross_domain_gaps(bundle: EvidenceBundle) -> list[ValidationGap]:
        """Extract validation gaps from cross-domain evidence."""
        gaps: list[ValidationGap] = []
        
        cross_domain_evidence = [
            ev for ev in bundle.impact_evidence
            if ev.evidence_type and "cross" in ev.evidence_type.lower()
        ]
        
        for ev in cross_domain_evidence[:3]:  # Limit to top 3
            try:
                source = ev.source.name if hasattr(ev.source, "name") else ""
                target = ev.target.name if hasattr(ev.target, "name") else ""
                
                if not source or not target:
                    continue
                
                # Cross-domain evidence often indicates missing integration tests
                gaps.append(ValidationGap(
                    description=f"No integration test verifies {source} → {target} cross-domain path",
                    invariant="Cross-domain execution must be validated",
                    existing_validation="Unit tests only",
                    missing_validation=f"Integration test for {source} → {target}",
                    affected_symbols=[source, target],
                    affected_domains=[],  # Would need to extract from evidence
                    confidence=ev.confidence,
                ))
            except Exception:
                continue
        
        return gaps
    
    @staticmethod
    def _deduplicate_gaps(gaps: list[ValidationGap]) -> list[ValidationGap]:
        """Remove duplicate gaps based on affected symbols."""
        seen_symbol_sets: set[str] = set()
        deduplicated: list[ValidationGap] = []
        
        for gap in gaps:
            # Create a key from sorted symbols
            symbol_key = ",".join(sorted(gap.affected_symbols))
            
            if symbol_key not in seen_symbol_sets:
                seen_symbol_sets.add(symbol_key)
                deduplicated.append(gap)
        
        return deduplicated
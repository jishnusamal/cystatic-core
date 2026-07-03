"""
Production Invariant Builder — generates deterministic invariants.

This module generates production invariants from business objects,
constraints, execution paths, and known templates.
"""
from __future__ import annotations

from typing import Any

from core_engine.models.normalized_facts import ProductionInvariant
from core_engine.models.evidence_bundle import EvidenceBundle


class InvariantBuilder:
    """Generates production invariants from deterministic analysis.
    
    Invariants are rules that must always hold in production.
    They are derived from business objects, constraints, and execution paths.
    """
    
    @staticmethod
    def build(
        bundle: EvidenceBundle,
        hypotheses: list[dict[str, Any]],
    ) -> list[ProductionInvariant]:
        """Build production invariants from evidence and hypotheses.
        
        Args:
            bundle: EvidenceBundle from EvidencePipeline.
            hypotheses: Generated impact hypotheses.
            
        Returns:
            List of ProductionInvariant objects.
        """
        invariants: list[ProductionInvariant] = []
        
        # Extract invariants from constraints
        invariants.extend(InvariantBuilder._extract_constraint_invariants(bundle))
        
        # Extract invariants from business objects
        invariants.extend(InvariantBuilder._extract_business_object_invariants(bundle))
        
        # Extract invariants from high-confidence hypotheses
        invariants.extend(InvariantBuilder._extract_hypothesis_invariants(hypotheses))
        
        # Extract invariants from known templates
        invariants.extend(InvariantBuilder._extract_template_invariants(bundle))
        
        # Deduplicate and limit
        invariants = InvariantBuilder._deduplicate_invariants(invariants)
        
        return invariants[:8]  # Limit to top 8 invariants
    
    @staticmethod
    def _extract_constraint_invariants(bundle: EvidenceBundle) -> list[ProductionInvariant]:
        """Extract invariants from constraints."""
        invariants: list[ProductionInvariant] = []
        
        for constraint in bundle.constraints[:5]:  # Limit to top 5
            try:
                constraint_type = constraint.constraint_type.value if hasattr(constraint.constraint_type, "value") else str(constraint.constraint_type)
                symbol = constraint.symbol if hasattr(constraint, "symbol") else ""
                description = constraint.description if hasattr(constraint, "description") else ""
                
                if not symbol:
                    continue
                
                # Convert constraint to invariant
                invariant_statement = InvariantBuilder._constraint_to_invariant(
                    constraint_type, symbol, description
                )
                
                if invariant_statement:
                    # Find related business objects
                    related_bos = [
                        bo.name for bo in bundle.business_objects
                        if bo.name and (bo.name.lower() in symbol.lower() or symbol.lower() in bo.name.lower())
                    ]
                    
                    invariants.append(ProductionInvariant(
                        statement=invariant_statement,
                        business_objects=related_bos[:3],
                        symbols=[symbol],
                        domains=bundle.domains[:3] if bundle.domains else [],
                        confidence=0.9,
                    ))
            except Exception:
                continue
        
        return invariants
    
    @staticmethod
    def _constraint_to_invariant(
        constraint_type: str,
        symbol: str,
        description: str,
    ) -> str:
        """Convert a constraint to an invariant statement."""
        constraint_lower = constraint_type.lower()
        
        # Transaction constraints
        if "transaction" in constraint_lower:
            return f"{symbol} operations must complete within transaction boundaries."
        
        # Validation constraints
        if "validation" in constraint_lower or "validate" in constraint_lower:
            return f"{symbol} must validate all inputs before processing."
        
        # State constraints
        if "state" in constraint_lower:
            return f"{symbol} state transitions must follow defined workflow."
        
        # Authorization constraints
        if "auth" in constraint_lower or "permission" in constraint_lower:
            return f"{symbol} must verify authorization before execution."
        
        # Data integrity constraints
        if "integrity" in constraint_lower or "consistency" in constraint_lower:
            return f"{symbol} must maintain data integrity across operations."
        
        # Use description if available
        if description:
            return f"{symbol}: {description}"
        
        # Generic constraint
        return f"{symbol} must satisfy {constraint_type} constraint."
    
    @staticmethod
    def _extract_business_object_invariants(bundle: EvidenceBundle) -> list[ProductionInvariant]:
        """Extract invariants from business objects."""
        invariants: list[ProductionInvariant] = []
        
        for bo in bundle.business_objects[:5]:  # Limit to top 5
            try:
                if not bo.name:
                    continue
                
                # Find related symbols
                related_symbols = [
                    cs.symbol for cs in bundle.changed_symbols
                    if bo.name.lower() in cs.symbol.lower() or cs.symbol.lower() in bo.name.lower()
                ]
                
                # Find related constraints
                related_constraints = [
                    c for c in bundle.constraints
                    if hasattr(c, "symbol") and c.symbol and bo.name.lower() in c.symbol.lower()
                ]
                
                # Generate invariant based on business object type
                invariant_statement = InvariantBuilder._business_object_to_invariant(
                    bo.name, related_constraints
                )
                
                if invariant_statement:
                    invariants.append(ProductionInvariant(
                        statement=invariant_statement,
                        business_objects=[bo.name],
                        symbols=related_symbols[:3],
                        domains=bundle.domains[:3] if bundle.domains else [],
                        confidence=0.85,
                    ))
            except Exception:
                continue
        
        return invariants
    
    @staticmethod
    def _business_object_to_invariant(
        bo_name: str,
        constraints: list[Any],
    ) -> str:
        """Convert a business object to an invariant statement."""
        bo_lower = bo_name.lower()
        
        # Payment-related invariants
        if any(keyword in bo_lower for keyword in ["payment", "checkout", "invoice"]):
            return f"Successful {bo_name} must create exactly one transaction record."
        
        # Order-related invariants
        if any(keyword in bo_lower for keyword in ["order", "cart"]):
            return f"{bo_name} state must only transition after payment confirmation."
        
        # Discount/coupon invariants
        if any(keyword in bo_lower for keyword in ["discount", "coupon", "promotion"]):
            return f"Expired {bo_name} must never reduce payable amount."
        
        # User/customer invariants
        if any(keyword in bo_lower for keyword in ["user", "customer", "account"]):
            return f"{bo_name} identity must be verified before state changes."
        
        # Inventory invariants
        if any(keyword in bo_lower for keyword in ["inventory", "stock", "product"]):
            return f"{bo_name} quantity must never be negative."
        
        # Generic invariant
        return f"{bo_name} must maintain consistency across all operations."
    
    @staticmethod
    def _extract_hypothesis_invariants(
        hypotheses: list[dict[str, Any]],
    ) -> list[ProductionInvariant]:
        """Extract invariants from high-confidence hypotheses."""
        invariants: list[ProductionInvariant] = []
        
        # Get high-confidence hypotheses
        high_conf = [h for h in hypotheses if h.get("confidence", 0) >= 0.7]
        
        for hyp in high_conf[:3]:  # Limit to top 3
            try:
                hypothesis_text = hyp.get("hypothesis", "")
                if not hypothesis_text:
                    continue
                
                # Check if hypothesis implies an invariant
                if any(keyword in hypothesis_text.lower() for keyword in [
                    "must", "should", "always", "never", "require", "depend"
                ]):
                    source = hyp.get("source_symbol", "")
                    target = hyp.get("target_symbol", "")
                    
                    if source or target:
                        symbol = source or target
                        invariants.append(ProductionInvariant(
                            statement=hypothesis_text[:200],
                            business_objects=hyp.get("affected_business_objects", [])[:3],
                            symbols=[source, target] if source and target else [symbol],
                            domains=hyp.get("affected_domains", [])[:3],
                            confidence=hyp.get("confidence", 0.7),
                        ))
            except Exception:
                continue
        
        return invariants
    
    @staticmethod
    def _extract_template_invariants(bundle: EvidenceBundle) -> list[ProductionInvariant]:
        """Extract invariants from known templates."""
        invariants: list[ProductionInvariant] = []
        
        # Check for common patterns
        has_payment = any("payment" in bo.name.lower() for bo in bundle.business_objects if bo.name)
        has_order = any("order" in bo.name.lower() for bo in bundle.business_objects if bo.name)
        has_discount = any("discount" in bo.name.lower() for bo in bundle.business_objects if bo.name)
        
        if has_payment and has_order:
            invariants.append(ProductionInvariant(
                statement="Payment confirmation must occur before order fulfillment.",
                business_objects=["Payment", "Order"],
                symbols=[],
                domains=bundle.domains[:2] if bundle.domains else [],
                confidence=0.8,
            ))
        
        if has_discount:
            invariants.append(ProductionInvariant(
                statement="Discount application must validate expiration and eligibility.",
                business_objects=["Discount"],
                symbols=[],
                domains=bundle.domains[:2] if bundle.domains else [],
                confidence=0.75,
            ))
        
        return invariants
    
    @staticmethod
    def _deduplicate_invariants(invariants: list[ProductionInvariant]) -> list[ProductionInvariant]:
        """Remove duplicate invariants based on statement similarity."""
        seen_statements: set[str] = set()
        deduplicated: list[ProductionInvariant] = []
        
        for invariant in invariants:
            # Normalize statement for comparison
            normalized = invariant.statement.lower().strip()
            
            if normalized not in seen_statements:
                seen_statements.add(normalized)
                deduplicated.append(invariant)
        
        return deduplicated
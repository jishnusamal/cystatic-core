"""
Domain Relationship Analyzer

Maps business-domain relationships.
Produces deterministic domain evidence.
"""
from __future__ import annotations

from typing import Any
from core_engine.analysers.base import EvidenceAnalyzer, AnalyzerOutput
from core_engine.analysers.analysis_context import AnalysisContext


class DomainRelationshipAnalyzer(EvidenceAnalyzer):
    """Map business-domain relationships.
    
    This analyzer:
    - Maps business objects to their domains
    - Identifies domain relationships
    - Never predicts failures
    - Only extracts deterministic domain relationship facts
    """
    
    # Domain relationship mappings
    DOMAIN_RELATIONSHIPS = {
        "payment": {
            "related_domains": ["billing", "order", "invoice", "subscription"],
            "business_objects": ["Payment", "Invoice", "Order"],
        },
        "billing": {
            "related_domains": ["payment", "invoice", "tax"],
            "business_objects": ["Invoice", "Payment", "Tax"],
        },
        "order": {
            "related_domains": ["payment", "fulfillment", "inventory"],
            "business_objects": ["Order", "Payment", "Shipment"],
        },
        "subscription": {
            "related_domains": ["payment", "billing", "notification"],
            "business_objects": ["Subscription", "Payment", "Invoice"],
        },
        "fulfillment": {
            "related_domains": ["order", "inventory", "notification"],
            "business_objects": ["Shipment", "Order", "Inventory"],
        },
        "inventory": {
            "related_domains": ["fulfillment", "order", "catalog"],
            "business_objects": ["Inventory", "Product", "Order"],
        },
        "auth": {
            "related_domains": ["identity", "user_management"],
            "business_objects": ["Customer", "User"],
        },
        "tax": {
            "related_domains": ["billing", "payment", "invoice"],
            "business_objects": ["Tax", "Invoice", "Payment"],
        },
    }
    
    def analyze(self, context: AnalysisContext) -> AnalyzerOutput:
        """Extract domain relationships from the analysis context.
        
        Args:
            context: AnalysisContext containing enriched_files and business_objects.
            
        Returns:
            AnalyzerOutput with impact_evidence for domain relationships.
        """
        output = AnalyzerOutput()
        
        # Collect all business objects and their domains
        business_objects_by_domain: dict[str, list[str]] = {}
        
        # Extract from business objects in context
        for bo in context.business_objects:
            bo_dict = self._to_dict(bo)
            domain = bo_dict.get("domain", "general")
            name = bo_dict.get("name", "")
            
            if domain not in business_objects_by_domain:
                business_objects_by_domain[domain] = []
            if name and name not in business_objects_by_domain[domain]:
                business_objects_by_domain[domain].append(name)
        
        # Also extract from enriched_files
        for file_data in context.enriched_files:
            file_path = file_data.get("file_path", "").lower()
            changed_functions = file_data.get("changed_functions", [])
            
            # Infer domain from file path
            domain = self._infer_domain_from_path(file_path)
            if domain and domain in self.DOMAIN_RELATIONSHIPS:
                # Add business objects for this domain
                if domain not in business_objects_by_domain:
                    business_objects_by_domain[domain] = []
                
                # Add default business objects for this domain
                for bo in self.DOMAIN_RELATIONSHIPS[domain]["business_objects"]:
                    if bo not in business_objects_by_domain[domain]:
                        business_objects_by_domain[domain].append(bo)
        
        # Generate impact evidence for domain relationships
        domains = list(business_objects_by_domain.keys())
        
        for i, domain1 in enumerate(domains):
            for domain2 in domains[i+1:]:
                # Check if domains are related
                relationship = self._get_domain_relationship(domain1, domain2)
                if relationship:
                    output.impact_evidence.append({
                        "source_symbol": domain1,
                        "target_symbol": domain2,
                        "evidence_type": "domain_relationship",
                        "confidence": 0.8,
                        "explanation": f"Domains '{domain1}' and '{domain2}' have a {relationship} relationship",
                        "metadata": {
                            "relationship_type": relationship,
                            "domain1_objects": business_objects_by_domain[domain1],
                            "domain2_objects": business_objects_by_domain[domain2],
                        },
                    })
        
        # Generate evidence for business objects within domains
        for domain, objects in business_objects_by_domain.items():
            if len(objects) > 1:
                # Multiple business objects in the same domain
                for i, obj1 in enumerate(objects):
                    for obj2 in objects[i+1:]:
                        output.impact_evidence.append({
                            "source_symbol": obj1,
                            "target_symbol": obj2,
                            "evidence_type": "shared_domain",
                            "confidence": 0.7,
                            "explanation": f"Both business objects belong to the '{domain}' domain",
                            "metadata": {
                                "domain": domain,
                            },
                        })
        
        return output
    
    def _infer_domain_from_path(self, file_path: str) -> str | None:
        """Infer domain from file path."""
        path_lower = file_path.lower()
        
        domain_keywords = {
            "payment": ["payment", "checkout", "billing"],
            "billing": ["billing", "invoice"],
            "order": ["order"],
            "subscription": ["subscription"],
            "fulfillment": ["fulfillment", "shipment"],
            "inventory": ["inventory"],
            "auth": ["auth", "authentication", "authorization"],
            "tax": ["tax"],
            "catalog": ["catalog", "product"],
            "notification": ["notification", "email", "sms"],
        }
        
        for domain, keywords in domain_keywords.items():
            if any(kw in path_lower for kw in keywords):
                return domain
        
        return None
    
    def _get_domain_relationship(self, domain1: str, domain2: str) -> str | None:
        """Get the relationship between two domains."""
        # Check if domain1 relates to domain2
        if domain1 in self.DOMAIN_RELATIONSHIPS:
            if domain2 in self.DOMAIN_RELATIONSHIPS[domain1]["related_domains"]:
                return "related"
        
        # Check if domain2 relates to domain1
        if domain2 in self.DOMAIN_RELATIONSHIPS:
            if domain1 in self.DOMAIN_RELATIONSHIPS[domain2]["related_domains"]:
                return "related"
        
        return None
    
    def _to_dict(self, value: Any) -> dict[str, Any]:
        """Convert value to dict."""
        if isinstance(value, dict):
            return value
        if hasattr(value, "model_dump"):
            return value.model_dump()
        return {}
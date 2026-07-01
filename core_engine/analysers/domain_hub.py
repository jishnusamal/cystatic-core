"""
Domain Hub Analyzer

Maps code artifacts to business domains and produces domain evidence.
This is the foundation for business-context reasoning.

Produces evidence types:
- belongs_to_domain
- touches_domain
- cross_domain_relationship
"""
from __future__ import annotations

from typing import Any
from core_engine.analysers.base import EvidenceAnalyzer, AnalyzerOutput
from core_engine.analysers.analysis_context import AnalysisContext
from core_engine.models.enums import EvidenceType


class DomainHubAnalyzer(EvidenceAnalyzer):
    """Map code artifacts to business domains.
    
    This analyzer:
    - Maps files, functions, and symbols to business domains
    - Identifies cross-domain relationships
    - Creates the semantic foundation for business-context reasoning
    - Never predicts failures
    - Only extracts deterministic domain facts
    """
    
    # Domain definitions with keywords and related domains
    DOMAINS = {
        "billing": {
            "keywords": ["billing", "invoice", "charge", "subscription_fee", "recurring"],
            "related_domains": ["payment", "tax", "subscription"],
            "business_objects": ["Invoice", "Payment", "Subscription", "Tax"],
        },
        "payment": {
            "keywords": ["payment", "checkout", "pay", "transaction", "stripe", "paypal"],
            "related_domains": ["billing", "order", "wallet"],
            "business_objects": ["Payment", "Transaction", "Wallet", "Checkout"],
        },
        "order": {
            "keywords": ["order", "purchase", "cart", "checkout"],
            "related_domains": ["payment", "fulfillment", "inventory"],
            "business_objects": ["Order", "Cart", "LineItem"],
        },
        "subscription": {
            "keywords": ["subscription", "recurring", "plan", "renewal", "cycle"],
            "related_domains": ["payment", "billing", "notification"],
            "business_objects": ["Subscription", "Plan", "Renewal"],
        },
        "tax": {
            "keywords": ["tax", "vat", "gst", "duty", "calculation"],
            "related_domains": ["billing", "payment", "invoice"],
            "business_objects": ["Tax", "TaxCalculation", "Invoice"],
        },
        "fulfillment": {
            "keywords": ["fulfillment", "shipment", "delivery", "shipping"],
            "related_domains": ["order", "inventory", "notification"],
            "business_objects": ["Shipment", "Fulfillment", "Delivery"],
        },
        "inventory": {
            "keywords": ["inventory", "stock", "warehouse", "sku"],
            "related_domains": ["fulfillment", "order", "catalog"],
            "business_objects": ["Inventory", "Stock", "Product"],
        },
        "auth": {
            "keywords": ["auth", "authentication", "authorization", "login", "oauth", "jwt"],
            "related_domains": ["identity", "user_management"],
            "business_objects": ["User", "Customer", "Session", "Token"],
        },
        "notification": {
            "keywords": ["notification", "email", "sms", "push", "notify"],
            "related_domains": ["subscription", "order", "fulfillment"],
            "business_objects": ["Notification", "Email", "SMS"],
        },
        "catalog": {
            "keywords": ["catalog", "product", "item", "sku", "price"],
            "related_domains": ["inventory", "order"],
            "business_objects": ["Product", "Catalog", "Price"],
        },
    }
    
    def analyze(self, context: AnalysisContext) -> AnalyzerOutput:
        """Extract domain information from the analysis context.
        
        Args:
            context: AnalysisContext containing enriched_files and changed symbols.
            
        Returns:
            AnalyzerOutput with domain evidence.
        """
        output = AnalyzerOutput()
        
        # Track domains found
        domains_found: dict[str, list[str]] = {}  # domain -> list of symbols
        
        # Extract from enriched files
        for file_data in context.enriched_files:
            file_path = file_data.get("file_path", "")
            changed_functions = file_data.get("changed_functions", [])
            
            # Infer domain from file path
            file_domain = self._infer_domain_from_path(file_path)
            if file_domain:
                if file_domain not in domains_found:
                    domains_found[file_domain] = []
                
                # Add file path as evidence
                output.impact_evidence.append({
                    "source_symbol": file_path,
                    "target_symbol": file_domain,
                    "evidence_type": "belongs_to_domain",
                    "confidence": 0.9,
                    "explanation": f"File path indicates {file_domain} domain",
                    "metadata": {
                        "artifact_type": "file",
                        "domain": file_domain,
                    },
                })
                domains_found[file_domain].append(file_path)
                
                # Add changed functions
                for func in changed_functions:
                    func_name = self._get_func_name(func)
                    if func_name:
                        output.impact_evidence.append({
                            "source_symbol": func_name,
                            "target_symbol": file_domain,
                            "evidence_type": "belongs_to_domain",
                            "confidence": 0.85,
                            "explanation": f"Function in {file_domain} domain file",
                            "metadata": {
                                "artifact_type": "function",
                                "domain": file_domain,
                                "file_path": file_path,
                            },
                        })
                        if func_name not in domains_found[file_domain]:
                            domains_found[file_domain].append(func_name)
            
            # Check keyword signals for domain hints
            keyword_signals = file_data.get("keyword_signals", [])
            for signal in keyword_signals:
                signal_text = signal.keyword if hasattr(signal, "keyword") else str(signal)
                signal_domain = self._infer_domain_from_keyword(signal_text)
                if signal_domain and signal_domain != file_domain:
                    # Cross-domain signal
                    output.impact_evidence.append({
                        "source_symbol": file_path,
                        "target_symbol": signal_domain,
                        "evidence_type": "touches_domain",
                        "confidence": 0.6,
                        "explanation": f"Keyword signal suggests {signal_domain} domain",
                        "metadata": {
                            "keyword": signal_text,
                            "primary_domain": file_domain,
                        },
                    })
        
        # Generate cross-domain relationships
        domains_list = list(domains_found.keys())
        for i, domain1 in enumerate(domains_list):
            for domain2 in domains_list[i+1:]:
                if self._are_domains_related(domain1, domain2):
                    output.impact_evidence.append({
                        "source_symbol": domain1,
                        "target_symbol": domain2,
                        "evidence_type": "cross_domain_relationship",
                        "confidence": 0.75,
                        "explanation": f"Domains '{domain1}' and '{domain2}' are architecturally related",
                        "metadata": {
                            "relationship_type": "related",
                            "domain1_symbols": domains_found[domain1][:5],  # Limit to 5
                            "domain2_symbols": domains_found[domain2][:5],
                        },
                    })
        
        # Add business objects for each domain
        for domain, symbols in domains_found.items():
            if domain in self.DOMAINS:
                for bo_name in self.DOMAINS[domain]["business_objects"]:
                    output.business_objects.append({
                        "name": bo_name,
                        "domain": domain,
                        "description": f"Business object in {domain} domain",
                    })
        
        return output
    
    def _infer_domain_from_path(self, file_path: str) -> str | None:
        """Infer domain from file path."""
        path_lower = file_path.lower()
        
        # Score each domain by keyword matches
        domain_scores: dict[str, int] = {}
        for domain, config in self.DOMAINS.items():
            score = sum(1 for kw in config["keywords"] if kw in path_lower)
            if score > 0:
                domain_scores[domain] = score
        
        # Return highest scoring domain
        if domain_scores:
            return max(domain_scores, key=domain_scores.get)
        
        return None
    
    def _infer_domain_from_keyword(self, keyword: str) -> str | None:
        """Infer domain from a keyword."""
        keyword_lower = keyword.lower()
        
        for domain, config in self.DOMAINS.items():
            if any(kw in keyword_lower for kw in config["keywords"]):
                return domain
        
        return None
    
    def _are_domains_related(self, domain1: str, domain2: str) -> bool:
        """Check if two domains are architecturally related."""
        if domain1 in self.DOMAINS:
            if domain2 in self.DOMAINS[domain1]["related_domains"]:
                return True
        
        if domain2 in self.DOMAINS:
            if domain1 in self.DOMAINS[domain2]["related_domains"]:
                return True
        
        return False
    
    def _get_func_name(self, func: Any) -> str:
        """Extract function name from function object."""
        if isinstance(func, dict):
            return func.get("name", "")
        if hasattr(func, "model_dump"):
            return func.model_dump().get("name", "")
        if hasattr(func, "name"):
            return func.name
        return ""
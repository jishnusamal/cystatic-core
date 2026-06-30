"""
Business Object Analyzer

Determines which business entities are affected by the change.
Produces: Invoice, Payment, Order, Wallet, Customer, Subscription, Refund, Shipment
"""
from __future__ import annotations

from typing import Any
from core_engine.analysers.base import EvidenceAnalyzer, AnalyzerOutput
from core_engine.analysers.analysis_context import AnalysisContext


class BusinessObjectAnalyzer(EvidenceAnalyzer):
    """Determine which business entities are affected by the change.
    
    This analyzer:
    - Identifies business objects referenced in the change
    - Maps file paths and symbols to business domains
    - Never performs business reasoning
    - Only extracts language-level facts about business object references
    """
    
    # Business object keywords
    BUSINESS_OBJECTS = {
        "invoice": "Invoice",
        "payment": "Payment",
        "order": "Order",
        "wallet": "Wallet",
        "customer": "Customer",
        "subscription": "Subscription",
        "refund": "Refund",
        "shipment": "Shipment",
        "tax": "Tax",
        "billing": "Billing",
        "checkout": "Checkout",
        "cart": "Cart",
        "product": "Product",
        "inventory": "Inventory",
        "fulfillment": "Fulfillment",
    }
    
    # Domain mapping
    DOMAIN_MAP = {
        "invoice": "billing",
        "payment": "payment",
        "order": "order",
        "wallet": "payment",
        "customer": "identity",
        "subscription": "subscription",
        "refund": "payment",
        "shipment": "fulfillment",
        "tax": "tax",
        "billing": "billing",
        "checkout": "checkout",
        "cart": "checkout",
        "product": "catalog",
        "inventory": "inventory",
        "fulfillment": "fulfillment",
    }
    
    def analyze(self, context: AnalysisContext) -> AnalyzerOutput:
        """Extract business objects from the analysis context.
        
        Args:
            context: AnalysisContext containing enriched_files and risk_patterns.
            
        Returns:
            AnalyzerOutput with business_objects populated.
        """
        output = AnalyzerOutput()
        
        # Extract from enriched_files
        for file_data in context.enriched_files:
            file_path = file_data.get("file_path", "").lower()
            changed_functions = file_data.get("changed_functions", [])
            keyword_signals = file_data.get("keyword_signals", [])
            
            # Check file path for business object references
            for keyword, business_object in self.BUSINESS_OBJECTS.items():
                if keyword in file_path:
                    domain = self.DOMAIN_MAP.get(keyword, "general")
                    output.business_objects.append({
                        "name": business_object,
                        "domain": domain,
                        "description": f"Business object referenced in file path: {file_path}",
                    })
            
            # Check changed function names
            for func in changed_functions:
                func_name = self._get_func_name(func).lower()
                for keyword, business_object in self.BUSINESS_OBJECTS.items():
                    if keyword in func_name:
                        domain = self.DOMAIN_MAP.get(keyword, "general")
                        # Avoid duplicates
                        if not any(bo["name"] == business_object for bo in output.business_objects):
                            output.business_objects.append({
                                "name": business_object,
                                "domain": domain,
                                "description": f"Business object referenced in function: {func_name}",
                            })
            
            # Check keyword signals
            for signal in keyword_signals:
                signal_dict = self._to_dict(signal)
                keyword = signal_dict.get("keyword", "").lower()
                for bo_keyword, business_object in self.BUSINESS_OBJECTS.items():
                    if bo_keyword in keyword:
                        domain = self.DOMAIN_MAP.get(bo_keyword, "general")
                        if not any(bo["name"] == business_object for bo in output.business_objects):
                            output.business_objects.append({
                                "name": business_object,
                                "domain": domain,
                                "description": f"Business object referenced in keyword signal: {keyword}",
                            })
        
        # Extract from risk patterns
        for risk_pattern in context.risk_patterns:
            risk_dict = self._to_dict(risk_pattern)
            domain = risk_dict.get("domain", "")
            
            # Map domain to business objects
            for keyword, business_object in self.BUSINESS_OBJECTS.items():
                if keyword in domain.lower():
                    if not any(bo["name"] == business_object for bo in output.business_objects):
                        output.business_objects.append({
                            "name": business_object,
                            "domain": self.DOMAIN_MAP.get(keyword, "general"),
                            "description": f"Business object inferred from risk pattern domain: {domain}",
                        })
        
        return output
    
    def _get_func_name(self, func: Any) -> str:
        """Extract function name from function object."""
        if isinstance(func, dict):
            return func.get("name", "")
        if hasattr(func, "model_dump"):
            return func.model_dump().get("name", "")
        if hasattr(func, "name"):
            return func.name
        return ""
    
    def _to_dict(self, value: Any) -> dict[str, Any]:
        """Convert value to dict."""
        if isinstance(value, dict):
            return value
        if hasattr(value, "model_dump"):
            return value.model_dump()
        return {}
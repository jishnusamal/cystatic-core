"""
Business Object Analyzer

Identifies business entities affected by changes and maps them to domains.
This creates the semantic glue between symbols, files, and domains.

Produces evidence types:
- shared_business_object
- business_object_reference
"""
from __future__ import annotations

from typing import Any
from core_engine.analysers.base import EvidenceAnalyzer, AnalyzerOutput
from core_engine.analysers.analysis_context import AnalysisContext
from core_engine.models.enums import EvidenceType


class BusinessObjectAnalyzer(EvidenceAnalyzer):
    """Identify business entities affected by changes.
    
    This analyzer:
    - Maps symbols, functions, and files to business objects
    - Identifies which business entities are touched by the change
    - Creates semantic connections between code and business concepts
    - Never performs business reasoning
    - Only extracts language-level facts about business object references
    """
    
    # Business object definitions with keywords and aliases
    BUSINESS_OBJECTS = {
        "Invoice": {
            "keywords": ["invoice", "billing", "charge", "receipt"],
            "aliases": ["Invoice", "BillingRecord", "ChargeRecord"],
            "domain": "billing",
        },
        "Payment": {
            "keywords": ["payment", "pay", "transaction", "checkout"],
            "aliases": ["Payment", "Transaction", "Checkout"],
            "domain": "payment",
        },
        "Order": {
            "keywords": ["order", "purchase", "cart"],
            "aliases": ["Order", "Purchase", "Cart"],
            "domain": "order",
        },
        "Customer": {
            "keywords": ["customer", "client", "buyer", "user"],
            "aliases": ["Customer", "Client", "User", "Buyer"],
            "domain": "identity",
        },
        "Subscription": {
            "keywords": ["subscription", "recurring", "plan", "renewal"],
            "aliases": ["Subscription", "Plan", "Renewal"],
            "domain": "subscription",
        },
        "Tax": {
            "keywords": ["tax", "vat", "gst", "duty"],
            "aliases": ["Tax", "TaxCalculation", "VAT", "GST"],
            "domain": "tax",
        },
        "Wallet": {
            "keywords": ["wallet", "balance", "credit", "funds"],
            "aliases": ["Wallet", "Balance", "Account"],
            "domain": "payment",
        },
        "Refund": {
            "keywords": ["refund", "reversal", "return"],
            "aliases": ["Refund", "Reversal", "Return"],
            "domain": "payment",
        },
        "Shipment": {
            "keywords": ["shipment", "delivery", "fulfillment", "shipping"],
            "aliases": ["Shipment", "Delivery", "Fulfillment"],
            "domain": "fulfillment",
        },
        "Product": {
            "keywords": ["product", "item", "catalog", "sku"],
            "aliases": ["Product", "Item", "CatalogItem"],
            "domain": "catalog",
        },
        "Inventory": {
            "keywords": ["inventory", "stock", "warehouse"],
            "aliases": ["Inventory", "Stock", "Warehouse"],
            "domain": "inventory",
        },
    }
    
    def analyze(self, context: AnalysisContext) -> AnalyzerOutput:
        """Extract business objects from the analysis context.
        
        Args:
            context: AnalysisContext containing enriched_files and changed symbols.
            
        Returns:
            AnalyzerOutput with business object evidence.
        """
        output = AnalyzerOutput()
        
        # Track business objects found
        objects_found: dict[str, list[str]] = {}  # business_object -> list of symbols
        
        # Extract from enriched files
        for file_data in context.enriched_files:
            file_path = file_data.get("file_path", "")
            changed_functions = file_data.get("changed_functions", [])
            keyword_signals = file_data.get("keyword_signals", [])
            
            # Check file path for business object references
            file_objects = self._detect_business_objects(file_path)
            for obj_name in file_objects:
                if obj_name not in objects_found:
                    objects_found[obj_name] = []
                objects_found[obj_name].append(file_path)
                
                output.impact_evidence.append({
                    "source_symbol": file_path,
                    "target_symbol": obj_name,
                    "evidence_type": "business_object_reference",
                    "confidence": 0.9,
                    "explanation": f"File path references {obj_name} business object",
                    "metadata": {
                        "artifact_type": "file",
                        "business_object": obj_name,
                        "domain": self.BUSINESS_OBJECTS.get(obj_name, {}).get("domain", "general"),
                    },
                })
            
            # Check changed function names
            for func in changed_functions:
                func_name = self._get_func_name(func)
                if func_name:
                    func_objects = self._detect_business_objects(func_name)
                    for obj_name in func_objects:
                        if obj_name not in objects_found:
                            objects_found[obj_name] = []
                        if func_name not in objects_found[obj_name]:
                            objects_found[obj_name].append(func_name)
                        
                        output.impact_evidence.append({
                            "source_symbol": func_name,
                            "target_symbol": obj_name,
                            "evidence_type": "business_object_reference",
                            "confidence": 0.85,
                            "explanation": f"Function name references {obj_name} business object",
                            "metadata": {
                                "artifact_type": "function",
                                "business_object": obj_name,
                                "domain": self.BUSINESS_OBJECTS.get(obj_name, {}).get("domain", "general"),
                                "file_path": file_path,
                            },
                        })
            
            # Check keyword signals
            for signal in keyword_signals:
                signal_text = signal.keyword if hasattr(signal, "keyword") else str(signal)
                signal_objects = self._detect_business_objects(signal_text)
                for obj_name in signal_objects:
                    if obj_name not in objects_found:
                        objects_found[obj_name] = []
                    if signal_text not in objects_found[obj_name]:
                        objects_found[obj_name].append(signal_text)
                    
                    output.impact_evidence.append({
                        "source_symbol": file_path,
                        "target_symbol": obj_name,
                        "evidence_type": "business_object_reference",
                        "confidence": 0.7,
                        "explanation": f"Keyword signal references {obj_name} business object",
                        "metadata": {
                            "artifact_type": "keyword_signal",
                            "business_object": obj_name,
                            "domain": self.BUSINESS_OBJECTS.get(obj_name, {}).get("domain", "general"),
                            "keyword": signal_text,
                        },
                    })
        
        # Generate shared business object evidence
        # If multiple symbols reference the same business object, they're connected
        for obj_name, symbols in objects_found.items():
            if len(symbols) > 1:
                # Multiple symbols reference this business object
                for i, sym1 in enumerate(symbols):
                    for sym2 in symbols[i+1:]:
                        output.impact_evidence.append({
                            "source_symbol": sym1,
                            "target_symbol": sym2,
                            "evidence_type": "shared_business_object",
                            "confidence": 0.75,
                            "explanation": f"Both reference {obj_name} business object",
                            "metadata": {
                                "business_object": obj_name,
                                "domain": self.BUSINESS_OBJECTS.get(obj_name, {}).get("domain", "general"),
                            },
                        })
        
        # Add business objects to output
        for obj_name, config in self.BUSINESS_OBJECTS.items():
            if obj_name in objects_found:
                output.business_objects.append({
                    "name": obj_name,
                    "domain": config["domain"],
                    "aliases": config["aliases"],
                    "description": f"Business object referenced in {len(objects_found[obj_name])} locations",
                    "referenced_by": objects_found[obj_name],
                })
        
        return output
    
    def _detect_business_objects(self, text: str) -> list[str]:
        """Detect business objects mentioned in text.
        
        Args:
            text: Text to analyze (file path, function name, etc.)
            
        Returns:
            List of business object names detected
        """
        text_lower = text.lower()
        detected = []
        
        for obj_name, config in self.BUSINESS_OBJECTS.items():
            # Check main keywords
            if any(kw in text_lower for kw in config["keywords"]):
                detected.append(obj_name)
                continue
            
            # Check aliases
            if any(alias.lower() in text_lower for alias in config["aliases"]):
                detected.append(obj_name)
        
        return detected
    
    def _get_func_name(self, func: Any) -> str:
        """Extract function name from function object."""
        if isinstance(func, dict):
            return func.get("name", "")
        if hasattr(func, "model_dump"):
            return func.model_dump().get("name", "")
        if hasattr(func, "name"):
            return func.name
        return ""
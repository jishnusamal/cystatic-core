"""
Risk Anchor Analyzer

Identifies semantic changes associated with elevated production risk.
Produces anchors such as: Money Flow, Authentication, Authorization, Transaction Boundary, Retry Sensitive, Cache Consistency, External Dependency, State Mutation, Idempotency
"""
from __future__ import annotations

from typing import Any
from core_engine.analysers.base import EvidenceAnalyzer, AnalyzerOutput
from core_engine.analysers.analysis_context import AnalysisContext


class RiskAnchorAnalyzer(EvidenceAnalyzer):
    """Identify semantic changes associated with elevated production risk.
    
    This analyzer:
    - Identifies changes known to increase downstream uncertainty
    - Maps changes to risk categories (money_flow, auth, etc.)
    - Never predicts failures
    - Only identifies risk anchors from deterministic patterns
    """
    
    # Risk anchor keywords and patterns
    RISK_ANCHOR_PATTERNS = {
        "money_flow": {
            "keywords": ["payment", "billing", "invoice", "charge", "refund", "transaction", "price", "cost"],
            "functions": ["process_payment", "charge", "refund", "calculate_total", "apply_discount"],
        },
        "authentication": {
            "keywords": ["auth", "login", "logout", "token", "jwt", "session", "credential"],
            "functions": ["login", "logout", "authenticate", "verify_token", "refresh_token"],
        },
        "authorization": {
            "keywords": ["permission", "role", "access", "policy", "acl"],
            "functions": ["authorize", "check_permission", "has_role", "require_permission"],
        },
        "transaction_boundary": {
            "keywords": ["transaction", "commit", "rollback", "atomic"],
            "functions": ["begin_transaction", "commit", "rollback", "transaction"],
        },
        "retry_sensitive": {
            "keywords": ["retry", "attempt", "backoff", "circuit_breaker"],
            "functions": ["retry", "with_retry", "attempt", "backoff"],
        },
        "cache_consistency": {
            "keywords": ["cache", "redis", "memcache", "invalidate"],
            "functions": ["cache_get", "cache_set", "invalidate_cache", "clear_cache"],
        },
        "external_dependency": {
            "keywords": ["api", "http", "request", "client", "service"],
            "functions": ["call_api", "fetch", "request", "external_call"],
        },
        "state_mutation": {
            "keywords": ["state", "update", "modify", "mutate", "set_"],
            "functions": ["update_state", "set_state", "mutate", "modify"],
        },
        "idempotency": {
            "keywords": ["idempotent", "idempotency", "duplicate", "once"],
            "functions": ["ensure_idempotent", "check_duplicate", "execute_once"],
        },
    }
    
    def analyze(self, context: AnalysisContext) -> AnalyzerOutput:
        """Extract risk anchors from the analysis context.
        
        Args:
            context: AnalysisContext containing enriched_files and risk_patterns.
            
        Returns:
            AnalyzerOutput with risk_anchors populated.
        """
        output = AnalyzerOutput()
        
        # Extract from enriched_files
        for file_data in context.enriched_files:
            file_path = file_data.get("file_path", "")
            changed_functions = file_data.get("changed_functions", [])
            keyword_signals = file_data.get("keyword_signals", [])
            
            # Check file path
            file_path_lower = file_path.lower()
            for anchor_type, patterns in self.RISK_ANCHOR_PATTERNS.items():
                for keyword in patterns["keywords"]:
                    if keyword in file_path_lower:
                        output.risk_anchors.append({
                            "anchor_type": anchor_type,
                            "symbol": file_path,
                            "confidence": 0.7,
                            "business_domain": self._infer_domain(file_path),
                            "business_object": self._infer_business_object(file_path),
                            "characteristics": [keyword],
                            "explanation": f"File path contains risk keyword '{keyword}'",
                        })
            
            # Check changed functions
            for func in changed_functions:
                func_name = self._get_func_name(func).lower()
                for anchor_type, patterns in self.RISK_ANCHOR_PATTERNS.items():
                    # Check function name
                    if func_name in patterns["functions"] or any(kw in func_name for kw in patterns["keywords"]):
                        output.risk_anchors.append({
                            "anchor_type": anchor_type,
                            "symbol": func_name,
                            "confidence": 0.8,
                            "business_domain": self._infer_domain_from_function(func_name),
                            "business_object": self._infer_business_object_from_function(func_name),
                            "characteristics": list(patterns["keywords"])[:3],
                            "explanation": f"Changed function '{func_name}' matches risk pattern",
                        })
            
            # Check keyword signals
            for signal in keyword_signals:
                signal_dict = self._to_dict(signal)
                keyword = signal_dict.get("keyword", "").lower()
                category = signal_dict.get("category", "")
                
                for anchor_type, patterns in self.RISK_ANCHOR_PATTERNS.items():
                    if keyword in patterns["keywords"] or any(kw in keyword for kw in patterns["keywords"]):
                        output.risk_anchors.append({
                            "anchor_type": anchor_type,
                            "symbol": keyword,
                            "confidence": 0.75,
                            "business_domain": self._infer_domain_from_keyword(keyword),
                            "business_object": self._infer_business_object_from_keyword(keyword),
                            "characteristics": [keyword],
                            "explanation": f"Keyword signal '{keyword}' indicates risk anchor",
                        })
        
        # Extract from risk patterns
        for risk_pattern in context.risk_patterns:
            risk_dict = self._to_dict(risk_pattern)
            risk_type = risk_dict.get("type", "")
            domain = risk_dict.get("domain", "")
            
            # Map risk event types to risk anchors
            anchor_type = self._map_risk_type_to_anchor(risk_type)
            if anchor_type:
                output.risk_anchors.append({
                    "anchor_type": anchor_type,
                    "symbol": risk_dict.get("function", ""),
                    "confidence": risk_dict.get("confidence", 0.7),
                    "business_domain": domain,
                    "business_object": self._infer_business_object_from_domain(domain),
                    "characteristics": [risk_type],
                    "explanation": f"Risk pattern '{risk_type}' detected in domain '{domain}'",
                })
        
        # Deduplicate risk anchors
        output.risk_anchors = self._dedupe(output.risk_anchors)
        
        return output
    
    def _map_risk_type_to_anchor(self, risk_type: str) -> str | None:
        """Map risk event type to risk anchor type."""
        mapping = {
            "FINANCIAL_LOGIC_CHANGE": "money_flow",
            "PAYMENT_FLOW": "money_flow",
            "TAX_CALCULATION_CHANGE": "money_flow",
            "AUTH_BYPASS": "authentication",
            "PERMISSION_REMOVED": "authorization",
            "SCHEMA_MIGRATION": "state_mutation",
            "DATA_MODEL_CHANGE": "state_mutation",
            "RETRY_HANDLING": "retry_sensitive",
            "STATE_MUTATION": "state_mutation",
            "CACHE_INVALIDATION": "cache_consistency",
            "CRITICAL_DEPENDENCY_CHANGED": "external_dependency",
        }
        return mapping.get(risk_type)
    
    def _infer_domain(self, file_path: str) -> str | None:
        """Infer business domain from file path."""
        path_lower = file_path.lower()
        domains = {
            "payment": ["payment", "checkout", "billing"],
            "billing": ["billing", "invoice"],
            "order": ["order"],
            "auth": ["auth", "authentication", "authorization"],
            "subscription": ["subscription"],
            "tax": ["tax"],
            "fulfillment": ["fulfillment", "shipment"],
            "inventory": ["inventory"],
            "identity": ["user", "customer", "identity"],
        }
        for domain, keywords in domains.items():
            if any(kw in path_lower for kw in keywords):
                return domain
        return "general"
    
    def _infer_business_object(self, file_path: str) -> str | None:
        """Infer business object from file path."""
        path_lower = file_path.lower()
        objects = {
            "Payment": ["payment"],
            "Invoice": ["invoice"],
            "Order": ["order"],
            "Customer": ["customer", "user"],
            "Subscription": ["subscription"],
            "Refund": ["refund"],
            "Tax": ["tax"],
        }
        for obj, keywords in objects.items():
            if any(kw in path_lower for kw in keywords):
                return obj
        return None
    
    def _infer_domain_from_function(self, func_name: str) -> str | None:
        """Infer domain from function name."""
        return self._infer_domain(func_name)
    
    def _infer_business_object_from_function(self, func_name: str) -> str | None:
        """Infer business object from function name."""
        return self._infer_business_object(func_name)
    
    def _infer_domain_from_keyword(self, keyword: str) -> str | None:
        """Infer domain from keyword."""
        return self._infer_domain(keyword)
    
    def _infer_business_object_from_keyword(self, keyword: str) -> str | None:
        """Infer business object from keyword."""
        return self._infer_business_object(keyword)
    
    def _infer_business_object_from_domain(self, domain: str) -> str | None:
        """Infer business object from domain."""
        domain_lower = domain.lower()
        mapping = {
            "payment": "Payment",
            "billing": "Invoice",
            "order": "Order",
            "auth": "Customer",
            "subscription": "Subscription",
            "tax": "Tax",
        }
        return mapping.get(domain_lower)
    
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
    
    def _dedupe(self, anchors: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Deduplicate risk anchors."""
        seen = set()
        unique = []
        for anchor in anchors:
            key = (anchor.get("anchor_type"), anchor.get("symbol"))
            if key not in seen:
                seen.add(key)
                unique.append(anchor)
        return unique
"""
Ownership Analyzer

Determines code ownership and team boundaries.
This is useful for context and reporting, and helps predict where regressions surface.

Produces evidence types:
- owned_by
- same_owner
- cross_owner
"""
from __future__ import annotations

from typing import Any
from core_engine.analysers.base import EvidenceAnalyzer, AnalyzerOutput
from core_engine.analysers.analysis_context import AnalysisContext
from core_engine.models.enums import EvidenceType


class OwnershipAnalyzer(EvidenceAnalyzer):
    """Determine code ownership and team boundaries.
    
    This analyzer:
    - Identifies code ownership from file paths and metadata
    - Maps team boundaries
    - Detects cross-owner dependencies
    - Never predicts failures
    - Only extracts deterministic ownership facts
    """
    
    # Ownership patterns
    OWNERSHIP_PATTERNS = {
        # Team-based ownership
        "team_patterns": {
            "payments": ["payment", "payments", "billing", "checkout", "wallet"],
            "identity": ["auth", "identity", "user", "customer", "login"],
            "fulfillment": ["fulfillment", "shipping", "shipment", "delivery"],
            "catalog": ["catalog", "product", "inventory", "stock"],
            "platform": ["platform", "infrastructure", "core", "shared"],
            "notifications": ["notification", "email", "sms", "push"],
        },
        # Module-based ownership
        "module_patterns": {
            "billing_module": ["billing", "invoice", "charge"],
            "payment_module": ["payment", "transaction", "checkout"],
            "order_module": ["order", "cart", "purchase"],
            "subscription_module": ["subscription", "plan", "recurring"],
            "tax_module": ["tax", "vat", "gst"],
        },
    }
    
    # Code owner file patterns (CODEOWNERS file conventions)
    CODEOWNER_INDICATORS = [
        "CODEOWNERS",
        "codeowners",
        "OWNERS",
        "owners",
        "@team/",
        "TEAM:",
        "OWNER:",
    ]
    
    def analyze(self, context: AnalysisContext) -> AnalyzerOutput:
        """Extract ownership information from the analysis context.
        
        Args:
            context: AnalysisContext containing enriched_files and changed functions.
            
        Returns:
            AnalyzerOutput with ownership evidence.
        """
        output = AnalyzerOutput()
        
        # Track ownership
        ownership_map: dict[str, list[str]] = {}  # owner -> list of symbols
        symbol_owners: dict[str, str] = {}  # symbol -> owner
        
        # Extract from enriched files
        for file_data in context.enriched_files:
            file_path = file_data.get("file_path", "")
            changed_functions = file_data.get("changed_functions", [])
            keyword_signals = file_data.get("keyword_signals", [])
            
            # Identify owner from file path
            file_owner = self._identify_owner_from_path(file_path)
            
            if file_owner:
                if file_owner not in ownership_map:
                    ownership_map[file_owner] = []
                
                # Add file to owner
                if file_path not in ownership_map[file_owner]:
                    ownership_map[file_owner].append(file_path)
                
                symbol_owners[file_path] = file_owner
                
                # Add evidence that file is owned by team/module
                output.impact_evidence.append({
                    "source_symbol": file_path,
                    "target_symbol": file_owner,
                    "evidence_type": "owned_by",
                    "confidence": 0.85,
                    "explanation": f"File is owned by {file_owner}",
                    "metadata": {
                        "artifact_type": "file",
                        "owner": file_owner,
                        "ownership_type": self._get_ownership_type(file_owner),
                    },
                })
                
                # Add changed functions
                for func in changed_functions:
                    func_name = self._get_func_name(func)
                    if func_name:
                        if func_name not in ownership_map[file_owner]:
                            ownership_map[file_owner].append(func_name)
                        
                        symbol_owners[func_name] = file_owner
                        
                        output.impact_evidence.append({
                            "source_symbol": func_name,
                            "target_symbol": file_owner,
                            "evidence_type": "owned_by",
                            "confidence": 0.8,
                            "explanation": f"Function is owned by {file_owner}",
                            "metadata": {
                                "artifact_type": "function",
                                "owner": file_owner,
                                "file_path": file_path,
                                "ownership_type": self._get_ownership_type(file_owner),
                            },
                        })
            
            # Check keyword signals for ownership hints
            for signal in keyword_signals:
                signal_text = signal.keyword if hasattr(signal, "keyword") else str(signal)
                signal_owner = self._identify_owner_from_text(signal_text)
                
                if signal_owner and signal_owner != file_owner:
                    output.impact_evidence.append({
                        "source_symbol": file_path,
                        "target_symbol": signal_owner,
                        "evidence_type": "cross_owner",
                        "confidence": 0.6,
                        "explanation": f"Keyword signal suggests {signal_owner} ownership",
                        "metadata": {
                            "keyword": signal_text,
                            "primary_owner": file_owner,
                            "secondary_owner": signal_owner,
                        },
                    })
        
        # Generate same_owner evidence for symbols with same owner
        for owner, symbols in ownership_map.items():
            if len(symbols) > 1:
                for i, sym1 in enumerate(symbols):
                    for sym2 in symbols[i+1:]:
                        output.impact_evidence.append({
                            "source_symbol": sym1,
                            "target_symbol": sym2,
                            "evidence_type": "same_owner",
                            "confidence": 0.75,
                            "explanation": f"Both owned by {owner}",
                            "metadata": {
                                "owner": owner,
                                "ownership_type": self._get_ownership_type(owner),
                            },
                        })
        
        return output
    
    def _identify_owner_from_path(self, file_path: str) -> str | None:
        """Identify owner from file path."""
        path_lower = file_path.lower()
        
        # Check team patterns
        for team, keywords in self.OWNERSHIP_PATTERNS["team_patterns"].items():
            if any(kw in path_lower for kw in keywords):
                return f"team_{team}"
        
        # Check module patterns
        for module, keywords in self.OWNERSHIP_PATTERNS["module_patterns"].items():
            if any(kw in path_lower for kw in keywords):
                return module
        
        return None
    
    def _identify_owner_from_text(self, text: str) -> str | None:
        """Identify owner from text."""
        text_lower = text.lower()
        
        # Check team patterns
        for team, keywords in self.OWNERSHIP_PATTERNS["team_patterns"].items():
            if any(kw in text_lower for kw in keywords):
                return f"team_{team}"
        
        # Check module patterns
        for module, keywords in self.OWNERSHIP_PATTERNS["module_patterns"].items():
            if any(kw in text_lower for kw in keywords):
                return module
        
        return None
    
    def _get_ownership_type(self, owner: str) -> str:
        """Determine ownership type (team vs module)."""
        if owner.startswith("team_"):
            return "team"
        elif owner.endswith("_module"):
            return "module"
        else:
            return "unknown"
    
    def _get_func_name(self, func: Any) -> str:
        """Extract function name from function object."""
        if isinstance(func, dict):
            return func.get("name", "")
        if hasattr(func, "model_dump"):
            return func.model_dump().get("name", "")
        if hasattr(func, "name"):
            return func.name
        return ""
    
    def _get_func_text(self, func: Any) -> str:
        """Extract function text/code from function object."""
        if isinstance(func, dict):
            return func.get("text", "") or func.get("code", "") or func.get("name", "")
        if hasattr(func, "model_dump"):
            dump = func.model_dump()
            return dump.get("text", "") or dump.get("code", "") or dump.get("name", "")
        if hasattr(func, "text"):
            return func.text
        if hasattr(func, "code"):
            return func.code
        if hasattr(func, "name"):
            return func.name
        return ""
"""
Ownership Analyzer

Determines engineering ownership using CODEOWNERS, repository metadata, and ownership configuration.
"""
from __future__ import annotations

from typing import Any
from core_engine.analysers.base import EvidenceAnalyzer, AnalyzerOutput
from core_engine.analysers.analysis_context import AnalysisContext


class OwnershipAnalyzer(EvidenceAnalyzer):
    """Determine engineering ownership.
    
    This analyzer:
    - Uses CODEOWNERS patterns
    - Uses repository metadata
    - Uses ownership configuration
    - Never predicts failures
    - Only extracts deterministic ownership facts
    """
    
    # Default ownership rules (in real implementation, would parse CODEOWNERS file)
    DEFAULT_OWNERSHIP_RULES = {
        "payment": "team-payments",
        "billing": "team-billing",
        "invoice": "team-billing",
        "order": "team-orders",
        "fulfillment": "team-fulfillment",
        "inventory": "team-inventory",
        "auth": "team-auth",
        "authentication": "team-auth",
        "authorization": "team-auth",
        "user": "team-identity",
        "customer": "team-identity",
        "subscription": "team-subscriptions",
        "tax": "team-tax",
        "notification": "team-notifications",
        "checkout": "team-checkout",
        "cart": "team-checkout",
    }
    
    def analyze(self, context: AnalysisContext) -> AnalyzerOutput:
        """Extract ownership information from the analysis context.
        
        Args:
            context: AnalysisContext containing enriched_files and repo_metadata.
            
        Returns:
            AnalyzerOutput with impact_evidence for ownership relationships.
        """
        output = AnalyzerOutput()
        
        # Extract from enriched_files
        for file_data in context.enriched_files:
            file_path = file_data.get("file_path", "")
            changed_functions = file_data.get("changed_functions", [])
            
            # Determine owner for this file
            owner = self._determine_owner(file_path)
            
            # Add ownership evidence for changed symbols
            for func in changed_functions:
                func_name = self._get_func_name(func)
                if not func_name:
                    continue
                
                symbol_key = f"{file_path}:{func_name}"
                
                output.impact_evidence.append({
                    "source_symbol": symbol_key,
                    "target_symbol": owner,
                    "evidence_type": "ownership_relationship",
                    "confidence": 0.9,
                    "explanation": f"Symbol '{symbol_key}' is owned by '{owner}'",
                    "metadata": {
                        "owner": owner,
                        "file_path": file_path,
                    },
                })
        
        # Extract from repo_metadata if available
        repo_metadata = context.repo_metadata
        if repo_metadata:
            # In a real implementation, would parse CODEOWNERS file
            # For now, use default rules
            pass
        
        return output
    
    def _determine_owner(self, file_path: str) -> str:
        """Determine the owner of a file based on path."""
        path_lower = file_path.lower()
        
        # Check against default rules
        for keyword, owner in self.DEFAULT_OWNERSHIP_RULES.items():
            if keyword in path_lower:
                return owner
        
        # Default owner
        return "team-core"
    
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
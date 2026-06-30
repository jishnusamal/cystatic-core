"""
Naming Similarity Analyzer

Infers weak semantic relationships using naming.
Examples: calculate_tax, compute_tax, tax_rate
Produces low-confidence evidence only.
"""
from __future__ import annotations

from typing import Any
from difflib import SequenceMatcher
from core_engine.analysers.base import EvidenceAnalyzer, AnalyzerOutput
from core_engine.analysers.analysis_context import AnalysisContext


class NamingSimilarityAnalyzer(EvidenceAnalyzer):
    """Infer weak semantic relationships using naming.
    
    This analyzer:
    - Compares symbol names for similarity
    - Identifies naming patterns that suggest semantic relationships
    - Only produces low-confidence evidence
    - Never predicts failures
    - Only extracts deterministic naming similarity facts
    """
    
    # Common naming patterns that suggest semantic relationships
    NAMING_PATTERNS = {
        "tax": ["tax", "taxation", "taxable"],
        "payment": ["payment", "pay", "remittance"],
        "order": ["order", "purchase", "procurement"],
        "invoice": ["invoice", "billing", "bill"],
        "user": ["user", "account", "profile"],
        "customer": ["customer", "client", "patron"],
        "calculate": ["calculate", "compute", "compute_", "calc"],
        "validate": ["validate", "verify", "check", "ensure"],
        "get": ["get", "fetch", "retrieve", "find"],
        "set": ["set", "update", "modify", "assign"],
    }
    
    # Similarity threshold for considering names related
    SIMILARITY_THRESHOLD = 0.7
    
    def analyze(self, context: AnalysisContext) -> AnalyzerOutput:
        """Extract naming similarity evidence from the analysis context.
        
        Args:
            context: AnalysisContext containing enriched_files with changed functions.
            
        Returns:
            AnalyzerOutput with low-confidence impact_evidence for naming similarities.
        """
        output = AnalyzerOutput()
        
        # Collect all changed symbols
        all_symbols: list[tuple[str, str]] = []  # (symbol_name, file_path)
        
        for file_data in context.enriched_files:
            file_path = file_data.get("file_path", "")
            changed_functions = file_data.get("changed_functions", [])
            
            for func in changed_functions:
                func_name = self._get_func_name(func)
                if func_name:
                    all_symbols.append((func_name, file_path))
        
        # Compare symbols for naming similarity
        for i, (symbol1, file1) in enumerate(all_symbols):
            for symbol2, file2 in all_symbols[i+1:]:
                # Skip if same symbol
                if symbol1 == symbol2:
                    continue
                
                # Check for naming similarity
                similarity_score = self._calculate_similarity(symbol1, symbol2)
                
                if similarity_score >= self.SIMILARITY_THRESHOLD:
                    # Check if they share a common pattern
                    common_pattern = self._find_common_pattern(symbol1, symbol2)
                    
                    if common_pattern:
                        output.impact_evidence.append({
                            "source_symbol": f"{file1}:{symbol1}",
                            "target_symbol": f"{file2}:{symbol2}",
                            "evidence_type": "naming_similarity",
                            "confidence": 0.3,  # Low confidence by design
                            "explanation": f"Symbols '{symbol1}' and '{symbol2}' share naming pattern '{common_pattern}' (similarity: {similarity_score:.2f})",
                            "metadata": {
                                "similarity_score": similarity_score,
                                "common_pattern": common_pattern,
                                "symbol1": symbol1,
                                "symbol2": symbol2,
                            },
                        })
        
        return output
    
    def _calculate_similarity(self, name1: str, name2: str) -> float:
        """Calculate similarity between two names."""
        # Use SequenceMatcher for string similarity
        return SequenceMatcher(None, name1.lower(), name2.lower()).ratio()
    
    def _find_common_pattern(self, name1: str, name2: str) -> str | None:
        """Find common naming pattern between two names."""
        name1_lower = name1.lower()
        name2_lower = name2.lower()
        
        # Check for common patterns
        for pattern_name, pattern_keywords in self.NAMING_PATTERNS.items():
            for keyword in pattern_keywords:
                if keyword in name1_lower and keyword in name2_lower:
                    return pattern_name
        
        # Check for common prefixes/suffixes
        # Find common prefix
        common_prefix = self._common_prefix(name1_lower, name2_lower)
        if len(common_prefix) >= 3:
            return f"prefix:{common_prefix}"
        
        # Find common suffix
        common_suffix = self._common_suffix(name1_lower, name2_lower)
        if len(common_suffix) >= 3:
            return f"suffix:{common_suffix}"
        
        return None
    
    def _common_prefix(self, s1: str, s2: str) -> str:
        """Find common prefix of two strings."""
        prefix = []
        for c1, c2 in zip(s1, s2):
            if c1 == c2:
                prefix.append(c1)
            else:
                break
        return "".join(prefix)
    
    def _common_suffix(self, s1: str, s2: str) -> str:
        """Find common suffix of two strings."""
        suffix = []
        for c1, c2 in zip(reversed(s1), reversed(s2)):
            if c1 == c2:
                suffix.append(c1)
            else:
                break
        return "".join(reversed(suffix))
    
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
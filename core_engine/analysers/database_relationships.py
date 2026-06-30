"""
Database Relationship Analyzer

Discovers operational coupling through shared persistence.
Produces evidence such as: Reads Same Table, Writes Same Table, Shared Model, Shared Collection
"""
from __future__ import annotations

from typing import Any
from core_engine.analysers.base import EvidenceAnalyzer, AnalyzerOutput
from core_engine.analysers.analysis_context import AnalysisContext


class DatabaseRelationshipAnalyzer(EvidenceAnalyzer):
    """Discover operational coupling through shared persistence.
    
    This analyzer:
    - Identifies database table access patterns
    - Detects shared models between changed symbols
    - Never predicts failures
    - Only extracts deterministic database relationship facts
    """
    
    # Database operation patterns
    TABLE_PATTERNS = {
        "save": "write",
        "update": "write",
        "insert": "write",
        "delete": "write",
        "commit": "write",
        "query": "read",
        "filter": "read",
        "get": "read",
        "find": "read",
        "select": "read",
    }
    
    # Common table/model name patterns
    MODEL_PATTERNS = [
        "model", "table", "schema", "entity",
        "User", "Order", "Payment", "Invoice",
        "Customer", "Product", "Subscription",
    ]
    
    def analyze(self, context: AnalysisContext) -> AnalyzerOutput:
        """Extract database relationships from the analysis context.
        
        Args:
            context: AnalysisContext containing enriched_files with hunks.
            
        Returns:
            AnalyzerOutput with impact_evidence for database relationships.
        """
        output = AnalyzerOutput()
        
        # Track tables/models accessed by each changed symbol
        symbol_tables: dict[str, list[str]] = {}
        
        # Extract from enriched_files
        for file_data in context.enriched_files:
            file_path = file_data.get("file_path", "")
            changed_functions = file_data.get("changed_functions", [])
            hunks = file_data.get("hunks", [])
            
            # Get added lines
            added_lines = self._extract_added_lines(hunks)
            
            # For each changed function, detect database operations
            for func in changed_functions:
                func_name = self._get_func_name(func)
                if not func_name:
                    continue
                
                symbol_key = f"{file_path}:{func_name}"
                tables_accessed = []
                
                # Check added lines for database operations
                for line in added_lines:
                    line_lower = line.lower()
                    
                    # Detect table/model references
                    for pattern in self.MODEL_PATTERNS:
                        if pattern.lower() in line_lower:
                            tables_accessed.append(pattern)
                    
                    # Detect operation types
                    for op_pattern, op_type in self.TABLE_PATTERNS.items():
                        if op_pattern in line_lower:
                            # Extract potential table name from the line
                            table_name = self._extract_table_name(line, op_pattern)
                            if table_name:
                                tables_accessed.append(table_name)
                
                if tables_accessed:
                    symbol_tables[symbol_key] = list(set(tables_accessed))
        
        # Generate impact evidence for shared tables
        symbols = list(symbol_tables.keys())
        for i, symbol1 in enumerate(symbols):
            for symbol2 in symbols[i+1:]:
                tables1 = set(symbol_tables[symbol1])
                tables2 = set(symbol_tables[symbol2])
                
                shared_tables = tables1.intersection(tables2)
                if shared_tables:
                    output.impact_evidence.append({
                        "source_symbol": symbol1,
                        "target_symbol": symbol2,
                        "evidence_type": "shared_database_table",
                        "confidence": 0.7,
                        "explanation": f"Both symbols access shared database tables: {', '.join(shared_tables)}",
                        "metadata": {
                            "shared_tables": list(shared_tables),
                            "symbol1_tables": list(tables1),
                            "symbol2_tables": list(tables2),
                        },
                    })
        
        return output
    
    def _extract_added_lines(self, hunks: list[Any]) -> list[str]:
        """Extract added lines from hunks."""
        added_lines = []
        
        for hunk in hunks:
            hunk_dict = self._to_dict(hunk)
            lines = hunk_dict.get("lines", [])
            
            for line in lines:
                line_dict = self._to_dict(line)
                if line_dict.get("line_type") == "added":
                    content = str(line_dict.get("content", ""))
                    if content.strip():
                        added_lines.append(content)
        
        return added_lines
    
    def _extract_table_name(self, line: str, operation: str) -> str | None:
        """Extract table name from a line containing a database operation."""
        # Simple heuristic: look for capitalized words after the operation
        # This is a simplified version - a real implementation would use AST parsing
        line_lower = line.lower()
        op_index = line_lower.find(operation)
        if op_index == -1:
            return None
        
        # Look for model/table names after the operation
        remainder = line[op_index + len(operation):]
        words = remainder.split()
        
        for word in words[:5]:  # Check next 5 words
            # Clean punctuation
            clean_word = word.strip("(),'\".")
            if clean_word and clean_word[0].isupper():
                return clean_word
        
        return None
    
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
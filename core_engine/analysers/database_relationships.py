"""
Database Relationship Analyzer

Extracts database table relationships and access patterns.
This connects otherwise unrelated code through shared persistence.

Produces evidence types:
- reads_table
- writes_table
- shares_table
- shared_database_entity
"""
from __future__ import annotations

from typing import Any
from core_engine.analysers.base import EvidenceAnalyzer, AnalyzerOutput
from core_engine.analysers.analysis_context import AnalysisContext
from core_engine.models.enums import EvidenceType


class DatabaseRelationshipAnalyzer(EvidenceAnalyzer):
    """Extract database table relationships and access patterns.
    
    This analyzer:
    - Identifies database tables referenced in code
    - Detects read/write patterns
    - Finds shared table access across functions
    - Never predicts failures
    - Only extracts deterministic database facts
    """
    
    # Common database table patterns
    TABLE_PATTERNS = {
        # ORM model patterns
        "orm_models": [
            "Model",
            "models.Model",
            "Base",
            "declarative_base",
            "Schema",
            "models.",
        ],
        # Query patterns
        "query_patterns": [
            ".objects.",
            ".query.",
            "select(",
            "insert(",
            "update(",
            "delete(",
            "filter(",
            "get(",
            "all(",
            "first(",
        ],
        # Transaction patterns (already in transaction analyzer, but relevant here)
        "db_operations": [
            "save(",
            "create(",
            "update(",
            "delete(",
            "bulk_create",
            "bulk_update",
        ],
    }
    
    # Table name extraction patterns
    TABLE_NAME_INDICATORS = [
        "table_name",
        "db_table",
        "__tablename__",
        "from ",
        "into ",
        "update ",
        "join ",
    ]
    
    def analyze(self, context: AnalysisContext) -> AnalyzerOutput:
        """Extract database relationships from the analysis context.
        
        Args:
            context: AnalysisContext containing enriched_files and changed functions.
            
        Returns:
            AnalyzerOutput with database relationship evidence.
        """
        output = AnalyzerOutput()
        
        # Track table access
        table_access: dict[str, dict[str, list[str]]] = {}  # table -> {"reads": [...], "writes": [...]}
        
        # Extract from enriched files
        for file_data in context.enriched_files:
            file_path = file_data.get("file_path", "")
            changed_functions = file_data.get("changed_functions", [])
            keyword_signals = file_data.get("keyword_signals", [])
            
            # Check changed functions for database patterns
            for func in changed_functions:
                func_name = self._get_func_name(func)
                if not func_name:
                    continue
                
                func_text = self._get_func_text(func)
                
                # Detect database operations
                db_ops = self._detect_database_operations(func_text, keyword_signals)
                
                for table_name, operations in db_ops.items():
                    if table_name not in table_access:
                        table_access[table_name] = {"reads": [], "writes": []}
                    
                    # Add evidence for each operation
                    for op in operations:
                        if op == "read":
                            evidence_type = "reads_table"
                            table_access[table_name]["reads"].append(func_name)
                        else:  # write
                            evidence_type = "writes_table"
                            table_access[table_name]["writes"].append(func_name)
                        
                        output.impact_evidence.append({
                            "source_symbol": func_name,
                            "target_symbol": table_name,
                            "evidence_type": evidence_type,
                            "confidence": 0.8,
                            "explanation": f"Function {func_name} {op}s from {table_name} table",
                            "metadata": {
                                "file_path": file_path,
                                "operation": op,
                                "table_name": table_name,
                            },
                        })
            
            # Check keyword signals for database hints
            for signal in keyword_signals:
                signal_text = signal.keyword if hasattr(signal, "keyword") else str(signal)
                tables = self._extract_table_names(signal_text)
                for table_name in tables:
                    if table_name not in table_access:
                        table_access[table_name] = {"reads": [], "writes": []}
                    
                    output.impact_evidence.append({
                        "source_symbol": file_path,
                        "target_symbol": table_name,
                        "evidence_type": "reads_table",
                        "confidence": 0.6,
                        "explanation": f"Keyword signal suggests access to {table_name}",
                        "metadata": {
                            "keyword": signal_text,
                            "file_path": file_path,
                        },
                    })
        
        # Generate shared table evidence
        # If multiple functions access the same table, they're connected
        for table_name, access in table_access.items():
            all_functions = access["reads"] + access["writes"]
            
            if len(all_functions) > 1:
                # Remove duplicates while preserving order
                unique_functions = list(dict.fromkeys(all_functions))
                
                for i, func1 in enumerate(unique_functions):
                    for func2 in unique_functions[i+1:]:
                        # Determine if they have different operation types
                        func1_reads = func1 in access["reads"]
                        func2_reads = func2 in access["reads"]
                        func1_writes = func1 in access["writes"]
                        func2_writes = func2 in access["writes"]
                        
                        if func1_reads and func2_writes:
                            explanation = f"{func1} reads and {func2} writes to {table_name}"
                        elif func1_writes and func2_reads:
                            explanation = f"{func1} writes and {func2} reads from {table_name}"
                        else:
                            explanation = f"Both access {table_name} table"
                        
                        output.impact_evidence.append({
                            "source_symbol": func1,
                            "target_symbol": func2,
                            "evidence_type": "shares_table",
                            "confidence": 0.75,
                            "explanation": explanation,
                            "metadata": {
                                "table_name": table_name,
                                "func1_operations": {
                                    "reads": func1_reads,
                                    "writes": func1_writes,
                                },
                                "func2_operations": {
                                    "reads": func2_reads,
                                    "writes": func2_writes,
                                },
                            },
                        })
        
        return output
    
    def _detect_database_operations(self, func_text: str, keyword_signals: list) -> dict[str, list[str]]:
        """Detect database operations in function text.
        
        Args:
            func_text: Function source code or metadata
            keyword_signals: List of keyword signals from analysis
            
        Returns:
            Dictionary mapping table names to list of operations ("read", "write")
        """
        table_operations: dict[str, list[str]] = {}
        text_lower = func_text.lower() if func_text else ""
        
        # Detect table names
        table_names = self._extract_table_names(func_text)
        
        if not table_names:
            return table_operations
        
        # Detect read operations
        read_patterns = ["select(", "filter(", "get(", "all(", "first(", "find("]
        has_read = any(pattern in text_lower for pattern in read_patterns)
        
        # Detect write operations
        write_patterns = ["insert(", "update(", "delete(", "save(", "create(", "bulk_create"]
        has_write = any(pattern in text_lower for pattern in write_patterns)
        
        # Check keyword signals for additional hints
        for signal in keyword_signals:
            signal_text = signal.keyword if hasattr(signal, "keyword") else str(signal)
            signal_lower = signal_text.lower()
            
            if any(rp in signal_lower for rp in read_patterns):
                has_read = True
            if any(wp in signal_lower for wp in write_patterns):
                has_write = True
        
        # Assign operations to tables
        for table_name in table_names:
            operations = []
            if has_read:
                operations.append("read")
            if has_write:
                operations.append("write")
            
            if operations:
                table_operations[table_name] = operations
        
        return table_operations
    
    def _extract_table_names(self, text: str) -> list[str]:
        """Extract table names from text.
        
        Args:
            text: Text to analyze
            
        Returns:
            List of table names detected
        """
        if not text:
            return []
        
        text_lower = text.lower()
        table_names = []
        
        # Look for common table name patterns
        # Pattern 1: Model class definitions (class Name(models.Model))
        import re
        model_pattern = r'class\s+(\w+)\s*\([^)]*Model[^)]*\)'
        matches = re.findall(model_pattern, text, re.IGNORECASE)
        for match in matches:
            # Convert CamelCase to snake_case (typical table naming)
            table_name = self._camel_to_snake(match)
            table_names.append(table_name)
        
        # Pattern 2: Explicit table names
        tablename_pattern = r'__tablename__\s*=\s*["\']([^"\']+)["\']'
        matches = re.findall(tablename_pattern, text, re.IGNORECASE)
        table_names.extend(matches)
        
        # Pattern 3: table_name attribute
        table_attr_pattern = r'table_name\s*=\s*["\']([^"\']+)["\']'
        matches = re.findall(table_attr_pattern, text, re.IGNORECASE)
        table_names.extend(matches)
        
        # Pattern 4: FROM/JOIN clauses (SQL-like)
        from_pattern = r'\bfrom\s+(\w+)'
        matches = re.findall(from_pattern, text_lower)
        table_names.extend(matches)
        
        join_pattern = r'\bjoin\s+(\w+)'
        matches = re.findall(join_pattern, text_lower)
        table_names.extend(matches)
        
        # Deduplicate and clean
        table_names = list(set(table_names))
        table_names = [name for name in table_names if len(name) > 2]  # Filter out very short names
        
        return table_names
    
    def _camel_to_snake(self, name: str) -> str:
        """Convert CamelCase to snake_case."""
        import re
        # Insert underscore before uppercase letters and convert to lowercase
        s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
        return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()
    
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
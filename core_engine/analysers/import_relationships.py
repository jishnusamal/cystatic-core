"""
Import Relationship Analyzer

Extracts compile-time dependencies.
Produces: Imports Symbol, Imports Module, Imports Package
"""
from __future__ import annotations

from typing import Any
from core_engine.analysers.base import EvidenceAnalyzer, AnalyzerOutput
from core_engine.analysers.analysis_context import AnalysisContext


class ImportRelationshipAnalyzer(EvidenceAnalyzer):
    """Extract compile-time dependencies.
    
    This analyzer:
    - Identifies import statements
    - Maps dependencies between modules
    - Never predicts failures
    - Only extracts deterministic import relationship facts
    """
    
    # Import patterns
    IMPORT_PATTERNS = {
        "python": [
            r"^import\s+([a-zA-Z_][a-zA-Z0-9_.]*)",
            r"^from\s+([a-zA-Z_][a-zA-Z0-9_.]*)\s+import",
        ],
        "javascript": [
            r"^import\s+.*from\s+['\"]([^'\"]+)['\"]",
            r"^const\s+.*=\s+require\(['\"]([^'\"]+)['\"]\)",
            r"^import\s+['\"]([^'\"]+)['\"]",
        ],
        "typescript": [
            r"^import\s+.*from\s+['\"]([^'\"]+)['\"]",
            r"^import\s+['\"]([^'\"]+)['\"]",
        ],
    }
    
    def analyze(self, context: AnalysisContext) -> AnalyzerOutput:
        """Extract import relationships from the analysis context.
        
        Args:
            context: AnalysisContext containing enriched_files with hunks.
            
        Returns:
            AnalyzerOutput with impact_evidence for import relationships.
        """
        output = AnalyzerOutput()
        
        # Extract from enriched_files
        for file_data in context.enriched_files:
            file_path = file_data.get("file_path", "")
            hunks = file_data.get("hunks", [])
            
            # Detect language from file extension
            language = self._detect_language(file_path)
            
            # Get added lines
            added_lines = self._extract_added_lines(hunks)
            
            # Check for imports in added lines
            for line in added_lines:
                imports = self._extract_imports(line, language)
                
                for import_info in imports:
                    output.impact_evidence.append({
                        "source_symbol": file_path,
                        "target_symbol": import_info["module"],
                        "evidence_type": import_info["type"],
                        "confidence": 0.9,
                        "explanation": f"File imports '{import_info['module']}' ({import_info['type']})",
                        "metadata": {
                            "import_type": import_info["type"],
                            "imported_module": import_info["module"],
                            "line": line[:200],
                        },
                    })
        
        # Also extract from ASTs if available
        if context.asts:
            for file_path, ast_data in context.asts.items():
                imports = self._extract_imports_from_ast(ast_data, file_path)
                for import_info in imports:
                    output.impact_evidence.append({
                        "source_symbol": file_path,
                        "target_symbol": import_info["module"],
                        "evidence_type": import_info["type"],
                        "confidence": 0.95,
                        "explanation": f"AST shows import of '{import_info['module']}' ({import_info['type']})",
                        "metadata": {
                            "import_type": import_info["type"],
                            "imported_module": import_info["module"],
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
    
    def _extract_imports(self, line: str, language: str) -> list[dict[str, str]]:
        """Extract imports from a line of code."""
        imports = []
        
        patterns = self.IMPORT_PATTERNS.get(language, [])
        
        for pattern in patterns:
            import re
            matches = re.findall(pattern, line, re.IGNORECASE)
            
            for match in matches:
                module = match.strip()
                if module:
                    # Determine import type
                    import_type = self._determine_import_type(line, module)
                    imports.append({
                        "module": module,
                        "type": import_type,
                    })
        
        return imports
    
    def _determine_import_type(self, line: str, module: str) -> str:
        """Determine the type of import."""
        line_lower = line.lower()
        
        if line_lower.startswith("import "):
            return "imports_module"
        elif line_lower.startswith("from "):
            return "imports_symbol"
        else:
            # Check for specific imports
            if "import " in line_lower:
                return "imports_symbol"
            return "imports_module"
    
    def _extract_imports_from_ast(self, ast_data: Any, file_path: str) -> list[dict[str, str]]:
        """Extract imports from AST data."""
        imports = []
        
        # This is a simplified version - a real implementation would parse the AST
        # For now, return empty list
        return imports
    
    def _detect_language(self, file_path: str) -> str:
        """Detect programming language from file extension."""
        if not file_path:
            return "python"
        
        ext = file_path.rsplit(".", 1)[-1].lower() if "." in file_path else ""
        language_map = {
            "py": "python",
            "js": "javascript",
            "ts": "typescript",
            "java": "java",
            "go": "go",
        }
        return language_map.get(ext, "python")
    
    def _to_dict(self, value: Any) -> dict[str, Any]:
        """Convert value to dict."""
        if isinstance(value, dict):
            return value
        if hasattr(value, "model_dump"):
            return value.model_dump()
        return {}
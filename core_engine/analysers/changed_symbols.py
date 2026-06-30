"""
Changed Symbol Analyzer

Extracts every modified symbol from the change.
Produces: Functions, Methods, Classes, Modules, Constants
"""
from __future__ import annotations

from typing import Any
from core_engine.analysers.base import EvidenceAnalyzer, AnalyzerOutput
from core_engine.analysers.analysis_context import AnalysisContext


class ChangedSymbolAnalyzer(EvidenceAnalyzer):
    """Extract every modified symbol from the change.
    
    This analyzer:
    - Extracts changed symbols from enriched_files
    - Classifies symbols by kind (function, method, class, etc.)
    - Never performs business reasoning
    - Never infers production failures
    - Only extracts language-level facts
    """
    
    def analyze(self, context: AnalysisContext) -> AnalyzerOutput:
        """Extract changed symbols from the analysis context.
        
        Args:
            context: AnalysisContext containing enriched_files with changed functions.
            
        Returns:
            AnalyzerOutput with changed_symbols populated.
        """
        output = AnalyzerOutput()
        
        # Extract from enriched_files
        for file_data in context.enriched_files:
            file_path = file_data.get("file_path", "")
            changed_functions = file_data.get("changed_functions", [])
            
            for func in changed_functions:
                # Handle both dict and object formats
                if isinstance(func, dict):
                    symbol_name = func.get("name", "")
                    symbol_kind = func.get("type", "function")
                elif hasattr(func, "model_dump"):
                    func_dict = func.model_dump()
                    symbol_name = func_dict.get("name", "")
                    symbol_kind = func_dict.get("type", "function")
                else:
                    symbol_name = getattr(func, "name", "")
                    symbol_kind = getattr(func, "type", "function")
                
                if not symbol_name:
                    continue
                
                # Normalize symbol kind
                kind = self._normalize_kind(symbol_kind)
                
                # Build changed symbol record
                symbol_record = {
                    "symbol": symbol_name,
                    "qualified_name": f"{file_path}:{symbol_name}",
                    "kind": kind,
                    "language": self._detect_language(file_path),
                    "file_path": file_path,
                    "module": self._extract_module(file_path),
                    "extraction_confidence": 1.0,
                }
                
                output.changed_symbols.append(symbol_record)
        
        return output
    
    def _normalize_kind(self, kind: str) -> str:
        """Normalize symbol kind to standard values."""
        kind_lower = kind.lower()
        if kind_lower in ("function", "fn", "def"):
            return "function"
        elif kind_lower in ("method", "fn_method"):
            return "method"
        elif kind_lower in ("class", "cls"):
            return "class"
        elif kind_lower in ("module", "file"):
            return "module"
        elif kind_lower in ("variable", "var"):
            return "variable"
        elif kind_lower in ("constant", "const"):
            return "constant"
        else:
            return "function"
    
    def _detect_language(self, file_path: str) -> str:
        """Detect programming language from file extension."""
        if not file_path:
            return "unknown"
        
        ext = file_path.rsplit(".", 1)[-1].lower() if "." in file_path else ""
        language_map = {
            "py": "python",
            "js": "javascript",
            "ts": "typescript",
            "java": "java",
            "go": "go",
            "rb": "ruby",
            "php": "php",
            "cs": "csharp",
            "cpp": "cpp",
            "c": "c",
            "rs": "rust",
            "swift": "swift",
            "kt": "kotlin",
        }
        return language_map.get(ext, "unknown")
    
    def _extract_module(self, file_path: str) -> str | None:
        """Extract module name from file path."""
        if not file_path:
            return None
        
        # Remove extension
        if "." in file_path:
            module = file_path.rsplit(".", 1)[0]
        else:
            module = file_path
        
        # Convert path separators to dots
        module = module.replace("/", ".").replace("\\", ".")
        
        # Remove leading dots
        module = module.lstrip(".")
        
        return module if module else None
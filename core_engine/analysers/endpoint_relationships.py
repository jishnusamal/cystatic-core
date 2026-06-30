"""
Endpoint Relationship Analyzer

Associates changes with public entry points.
Examples: REST, GraphQL, gRPC, CLI, Scheduled Jobs
"""
from __future__ import annotations

from typing import Any
from core_engine.analysers.base import EvidenceAnalyzer, AnalyzerOutput
from core_engine.analysers.analysis_context import AnalysisContext


class EndpointRelationshipAnalyzer(EvidenceAnalyzer):
    """Associate changes with public entry points.
    
    This analyzer:
    - Identifies REST endpoints
    - Identifies GraphQL resolvers
    - Identifies gRPC services
    - Identifies CLI commands
    - Identifies scheduled jobs
    - Never predicts failures
    - Only extracts deterministic endpoint facts
    """
    
    # Endpoint patterns
    ENDPOINT_PATTERNS = {
        "rest": {
            "decorators": ["@app.route", "@router.get", "@router.post", "@router.put", "@router.delete",
                          "def get_", "def post_", "def put_", "def delete_", "def patch_"],
            "keywords": ["endpoint", "route", "api", "view"],
        },
        "graphql": {
            "decorators": ["@query", "@mutation", "@subscription", "@resolver"],
            "keywords": ["graphql", "resolver", "schema"],
        },
        "grpc": {
            "decorators": ["@grpc.method", "@servicer"],
            "keywords": ["grpc", "protobuf", "servicer"],
        },
        "cli": {
            "decorators": ["@click.command", "@app.command", "@cli.command"],
            "keywords": ["cli", "command", "main"],
        },
        "scheduled": {
            "decorators": ["@scheduled", "@cron", "@periodic", "@task"],
            "keywords": ["cron", "schedule", "periodic", "job", "task"],
        },
    }
    
    def analyze(self, context: AnalysisContext) -> AnalyzerOutput:
        """Extract endpoint relationships from the analysis context.
        
        Args:
            context: AnalysisContext containing enriched_files with endpoints.
            
        Returns:
            AnalyzerOutput with impact_evidence for endpoint relationships.
        """
        output = AnalyzerOutput()
        
        # Extract from enriched_files
        for file_data in context.enriched_files:
            file_path = file_data.get("file_path", "")
            changed_functions = file_data.get("changed_functions", [])
            endpoints = file_data.get("endpoints", [])
            hunks = file_data.get("hunks", [])
            
            # Get added lines
            added_lines = self._extract_added_lines(hunks)
            
            # Process explicit endpoints from enriched_files
            for endpoint in endpoints:
                endpoint_dict = self._to_dict(endpoint)
                endpoint_type = endpoint_dict.get("type", "unknown")
                endpoint_name = endpoint_dict.get("function", "")
                
                if endpoint_name:
                    # Link changed functions to endpoints
                    for func in changed_functions:
                        func_name = self._get_func_name(func)
                        if func_name and (func_name == endpoint_name or func_name in endpoint_name):
                            output.impact_evidence.append({
                                "source_symbol": f"{file_path}:{func_name}",
                                "target_symbol": f"{file_path}:{endpoint_name}",
                                "evidence_type": "endpoint_implementation",
                                "confidence": 0.9,
                                "explanation": f"Function '{func_name}' implements endpoint '{endpoint_name}'",
                                "metadata": {
                                    "endpoint_type": endpoint_type,
                                    "endpoint_name": endpoint_name,
                                },
                            })
            
            # Also detect endpoints from added lines
            for line in added_lines:
                line_lower = line.lower()
                
                for endpoint_type, patterns in self.ENDPOINT_PATTERNS.items():
                    # Check decorators
                    for decorator in patterns["decorators"]:
                        if decorator.lower() in line_lower:
                            # Extract endpoint name
                            endpoint_name = self._extract_endpoint_name(line, decorator)
                            if endpoint_name:
                                output.impact_evidence.append({
                                    "source_symbol": file_path,
                                    "target_symbol": endpoint_name,
                                    "evidence_type": f"{endpoint_type}_endpoint",
                                    "confidence": 0.8,
                                    "explanation": f"Detected {endpoint_type} endpoint: {endpoint_name}",
                                    "metadata": {
                                        "endpoint_type": endpoint_type,
                                        "line": line[:200],
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
    
    def _extract_endpoint_name(self, line: str, decorator: str) -> str | None:
        """Extract endpoint name from a line containing a decorator."""
        import re
        
        # Look for function name after decorator
        # Pattern: @decorator(...)\ndef function_name(
        pattern = rf'{re.escape(decorator)}\s*\([^)]*\)\s*\n?\s*def\s+([a-zA-Z_][a-zA-Z0-9_]*)'
        match = re.search(pattern, line, re.IGNORECASE | re.MULTILINE)
        if match:
            return match.group(1)
        
        # Simpler pattern: just look for def function_name after decorator
        simple_pattern = rf'def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\('
        match = re.search(simple_pattern, line)
        if match:
            return match.group(1)
        
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
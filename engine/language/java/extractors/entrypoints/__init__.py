"""Java entrypoint extractor - detects REST API endpoints from Spring annotations."""

import re
from typing import Any

from engine.language.base import BaseExtractor


class JavaEntrypointExtractor(BaseExtractor):
    """
    Detects REST API endpoints from Spring MVC annotations.
    
    Produces a list of dicts with keys: method, route, handler.
    """
    
    def extract(self, tree: list[str], file_path: str) -> list[dict[str, Any]]:
        """
        Extract REST API endpoints from a Java source file.
        
        Args:
            tree: List of lines from the source file
            file_path: Path to the source file
            
        Returns:
            List of endpoint dicts
        """
        endpoints = []
        
        endpoint_patterns = [
            (r'@RequestMapping\s*\(.*?value\s*=\s*"([^"]+)"', None),
            (r'@GetMapping\s*\(.*?"([^"]+)"', 'GET'),
            (r'@PostMapping\s*\(.*?"([^"]+)"', 'POST'),
            (r'@PutMapping\s*\(.*?"([^"]+)"', 'PUT'),
            (r'@DeleteMapping\s*\(.*?"([^"]+)"', 'DELETE'),
            (r'@PatchMapping\s*\(.*?"([^"]+)"', 'PATCH'),
        ]
        
        for i, line in enumerate(tree, 1):
            for pattern, method in endpoint_patterns:
                match = re.search(pattern, line)
                if match:
                    route = match.group(1)
                    method_name = self._find_method_name(tree, i - 1)
                    
                    if method_name:
                        endpoints.append({
                            'method': method or 'GET',
                            'route': route,
                            'handler': method_name,
                        })
        
        return endpoints
    
    def _find_method_name(self, lines: list[str], start_idx: int) -> str | None:
        """Find the method name following an annotation."""
        method_pattern = r'(public|private|protected)?\s*\w+\s+(\w+)\s*\('
        
        for i in range(start_idx, min(start_idx + 5, len(lines))):
            match = re.search(method_pattern, lines[i])
            if match and 'class ' not in lines[i]:
                return match.group(2)
        
        return None
"""Java call extractor - extracts method calls from Java source."""

import re
from typing import Any

from engine.language.base import BaseExtractor


class JavaCallExtractor(BaseExtractor):
    """
    Extracts method call relationships from Java source files.
    
    Produces a list of dicts with keys: caller_id, callee_name, call_type.
    """
    
    def extract(self, tree: list[str], file_path: str) -> list[dict[str, Any]]:
        """
        Extract all method calls from a Java source file.
        
        Args:
            tree: List of lines from the source file
            file_path: Path to the source file
            
        Returns:
            List of call dicts
        """
        calls = []
        call_pattern = r'(\w+)\.(\w+)\s*\('
        
        for i, line in enumerate(tree, 1):
            for match in re.finditer(call_pattern, line):
                caller_name = match.group(1)
                callee_name = match.group(2)
                
                # Skip common noise
                if callee_name in ('main', 'println', 'print'):
                    continue
                
                caller_id = f"java://{file_path}::{caller_name}"
                
                calls.append({
                    'caller_id': caller_id,
                    'callee_name': callee_name,
                    'call_type': 'direct',
                })
        
        return calls
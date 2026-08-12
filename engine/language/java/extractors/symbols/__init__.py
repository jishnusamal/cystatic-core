"""Java symbol extractor - extracts classes, methods, and functions from Java source."""

import re
from typing import Any

from engine.language.base import BaseExtractor


class JavaSymbolExtractor(BaseExtractor):
    """
    Extracts class, method, and function definitions from Java source files.
    
    Produces a list of dicts with keys: type, name, start_line, end_line, 
    visibility, methods (for classes), properties.
    """
    
    def extract(self, tree: list[str], file_path: str) -> list[dict[str, Any]]:
        """
        Extract all symbols from a Java source file.
        
        Args:
            tree: List of lines from the source file
            file_path: Path to the source file
            
        Returns:
            List of symbol dicts
        """
        symbols = []
        content = '\n'.join(tree)
        
        # Extract classes
        for cls in self._extract_classes(content, tree):
            symbols.append(cls)
        
        # Extract top-level functions (outside classes)
        for func in self._extract_functions(content, tree):
            symbols.append(func)
        
        return symbols
    
    def _extract_classes(self, content: str, lines: list[str]) -> list[dict[str, Any]]:
        """Extract class definitions."""
        classes = []
        class_pattern = r'(public|private|protected)?\s*(abstract|final)?\s*class\s+(\w+)'
        
        for i, line in enumerate(lines, 1):
            match = re.search(class_pattern, line)
            if match:
                visibility = self._parse_visibility(match.group(1))
                class_name = match.group(3)
                end_line = self._find_block_end(lines, i - 1)
                
                methods = self._extract_methods_from_block(lines, i - 1, end_line)
                
                classes.append({
                    'type': 'class',
                    'name': class_name,
                    'start_line': i,
                    'end_line': end_line,
                    'visibility': visibility,
                    'methods': methods,
                    'properties': self._extract_class_properties(content),
                })
        
        return classes
    
    def _extract_methods_from_block(self, lines: list[str], start_idx: int, end_line: int) -> list[dict[str, Any]]:
        """Extract methods from a class block."""
        methods = []
        method_pattern = r'(public|private|protected)?\s*(static)?\s*\w+\s+(\w+)\s*\('
        
        for i in range(start_idx, min(end_line, len(lines))):
            line = lines[i]
            match = re.search(method_pattern, line)
            if match and 'class ' not in line:
                visibility = self._parse_visibility(match.group(1))
                method_name = match.group(3)
                method_end = self._find_block_end(lines, i)
                
                methods.append({
                    'name': method_name,
                    'start_line': i + 1,
                    'end_line': method_end,
                    'class_name': '',
                    'visibility': visibility,
                })
        
        return methods
    
    def _extract_functions(self, content: str, lines: list[str]) -> list[dict[str, Any]]:
        """Extract top-level functions (methods not in classes)."""
        functions = []
        method_pattern = r'(public|private|protected)?\s*(static)?\s*\w+\s+(\w+)\s*\('
        
        for i, line in enumerate(lines, 1):
            if self._is_inside_class(lines, i - 1):
                continue
            
            match = re.search(method_pattern, line)
            if match and 'class ' not in line:
                visibility = self._parse_visibility(match.group(1))
                func_name = match.group(3)
                end_line = self._find_block_end(lines, i - 1)
                
                functions.append({
                    'type': 'function',
                    'name': func_name,
                    'start_line': i,
                    'end_line': end_line,
                    'visibility': visibility,
                    'properties': {},
                })
        
        return functions
    
    def _parse_visibility(self, visibility_str: str | None) -> str:
        """Parse Java visibility modifier."""
        return visibility_str or 'public'
    
    def _is_inside_class(self, lines: list[str], line_idx: int) -> bool:
        """Check if a line is inside a class definition."""
        if line_idx < 0 or line_idx >= len(lines):
            return False
        
        open_braces = 0
        for i in range(line_idx):
            line = lines[i]
            open_braces += line.count('{') - line.count('}')
        
        return open_braces > 0
    
    def _find_block_end(self, lines: list[str], start_idx: int) -> int:
        """Find the end line of a code block."""
        brace_count = 0
        found_open = False
        
        for i in range(start_idx, len(lines)):
            line = lines[i]
            
            if not found_open:
                if '{' in line:
                    found_open = True
                    brace_count = 1
            else:
                brace_count += line.count('{') - line.count('}')
                
                if brace_count <= 0:
                    return i + 1
        
        return min(start_idx + 10, len(lines))
    
    def _extract_class_properties(self, content: str) -> dict[str, Any]:
        """Extract additional properties from a class."""
        properties = {}
        if '@Entity' in content:
            properties['is_entity'] = True
        if '@RestController' in content or '@Controller' in content:
            properties['is_controller'] = True
        return properties
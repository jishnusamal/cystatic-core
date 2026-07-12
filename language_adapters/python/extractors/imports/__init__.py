"""Python import extractor - extracts import statements from Python AST."""

import ast
from typing import Any

from language_adapters.base import BaseExtractor


class PythonImportExtractor(BaseExtractor):
    """
    Extracts import statements from Python source files.
    
    Produces a list of dicts with keys: type, module, names.
    """
    
    def extract(self, tree: ast.AST, file_path: str) -> list[dict[str, Any]]:
        """
        Extract all imports from a Python AST.
        
        Args:
            tree: Parsed Python AST
            file_path: Path to the source file
            
        Returns:
            List of import dicts with type, module, names
        """
        imports = []
        
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ''
                names = [alias.name for alias in node.names]
                imports.append({
                    'type': 'from_import',
                    'module': module,
                    'names': names,
                })
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append({
                        'type': 'import',
                        'module': alias.name,
                        'names': [alias.name],
                    })
        
        return imports
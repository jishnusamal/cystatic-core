"""Java import extractor - extracts import statements from Java source."""

import re
from typing import Any

from language_adapters.base import BaseExtractor


class JavaImportExtractor(BaseExtractor):
    """
    Extracts import statements from Java source files.
    
    Produces a list of dicts with keys: type, module, names.
    """
    
    def extract(self, tree: list[str], file_path: str) -> list[dict[str, Any]]:
        """
        Extract all imports from a Java source file.
        
        Args:
            tree: List of lines from the source file
            file_path: Path to the source file
            
        Returns:
            List of import dicts
        """
        content = '\n'.join(tree) if isinstance(tree, list) else str(tree)
        imports = []
        
        import_pattern = r'import\s+(static\s+)?([\w.]+);'
        
        for match in re.finditer(import_pattern, content):
            is_static = match.group(1) is not None
            module = match.group(2)
            
            imports.append({
                'type': 'from_import' if is_static else 'import',
                'module': module,
                'names': [module.split('.')[-1]],
            })
        
        return imports
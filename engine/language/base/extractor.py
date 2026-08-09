"""Base extractor interface - defines the contract for language-specific extractors."""

from abc import ABC, abstractmethod
from typing import Any


class BaseExtractor(ABC):
    """
    Abstract base class for all extractors.
    
    Each extractor is responsible for extracting a specific type of 
    semantic information from source code (e.g., symbols, imports, calls).
    """
    
    @abstractmethod
    def extract(self, tree: Any, file_path: str) -> list[dict[str, Any]]:
        """
        Extract semantic information from a parsed file.
        
        Args:
            tree: Parsed AST or representation of the file
            file_path: Path to the source file
            
        Returns:
            List of extracted data dictionaries
        """
        pass
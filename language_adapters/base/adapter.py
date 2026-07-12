"""Base language adapter - abstract interface for all language adapters."""

from abc import ABC, abstractmethod
from typing import Any

from language_adapters.model import RepositoryModel


class BaseLanguageAdapter(ABC):
    """
    Abstract base class for language adapters.
    
    All language adapters must implement this interface to ensure
    they produce a deterministic RepositoryModel.
    """
    
    @abstractmethod
    def get_language(self) -> str:
        """
        Get the language name this adapter handles.
        
        Returns:
            Language identifier (e.g., "python", "java")
        """
        pass
    
    @abstractmethod
    def compile(self, repository_input: dict[str, Any]) -> RepositoryModel:
        """
        Compile a repository into a RepositoryModel.
        
        Args:
            repository_input: Repository snapshot containing:
                - root_directory: str
                - language: str
                - files: dict[file_path, file_content]
        
        Returns:
            RepositoryModel: Language-independent repository representation
        """
        pass
    
    @abstractmethod
    def get_compiler_passes(self) -> list[str]:
        """
        Get the names of compiler passes this adapter uses.
        
        Returns:
            List of pass names in execution order
        """
        pass
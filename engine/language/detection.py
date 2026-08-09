"""Language detection and adapter factory.

Simple language detection based on repository file extensions.
Returns the appropriate language adapter for compilation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.errors import LanguageDetectionFailed, LanguageNotSupported

if TYPE_CHECKING:
    from engine.language.base import BaseLanguageAdapter


# Language detection rules - ordered by priority
LANGUAGE_RULES = [
    ("python", {".py"}),
    ("java", {".java"}),
    ("go", {".go"}),
    ("typescript", {".ts", ".tsx"}),
    ("javascript", {".js", ".jsx"}),
]


class LanguageAdapterFactory:
    """
    Factory for creating language adapters based on repository content.
    
    Detects the primary language of a repository and returns the appropriate
    adapter for compilation.
    """
    
    def __init__(self) -> None:
        """Initialize the factory with adapter registry."""
        self._adapters: dict[str, type[BaseLanguageAdapter]] = {}
        self._register_default_adapters()
    
    def _register_default_adapters(self) -> None:
        """Register built-in language adapters."""
        # Import adapters here to avoid circular imports
        try:
            from language_adapters.python.adapter import PythonLanguageAdapter
            self._adapters["python"] = PythonLanguageAdapter
        except ImportError:
            pass
        
        try:
            from language_adapters.java.adapter import JavaLanguageAdapter
            self._adapters["java"] = JavaLanguageAdapter
        except ImportError:
            pass
    
    def detect_language(self, files: dict[str, str]) -> str:
        """
        Detect the primary language of a repository from its files.
        
        Args:
            files: Dictionary mapping file paths to file contents
            
        Returns:
            Detected language name (e.g., "python", "java")
            
        Raises:
            LanguageDetectionFailed: If language cannot be detected
        """
        if not files:
            raise LanguageDetectionFailed("No files provided for language detection")
        
        # Count file extensions
        extension_counts: dict[str, int] = {}
        for file_path in files.keys():
            ext = self._get_extension(file_path)
            if ext:
                extension_counts[ext] = extension_counts.get(ext, 0) + 1
        
        if not extension_counts:
            raise LanguageDetectionFailed("No recognizable file extensions found")
        
        # Match against language rules
        for language, extensions in LANGUAGE_RULES:
            for ext in extensions:
                if ext in extension_counts:
                    return language
        
        # If no match, return the most common extension's language
        most_common_ext = max(extension_counts.items(), key=lambda x: x[1])[0]
        for language, extensions in LANGUAGE_RULES:
            if most_common_ext in extensions:
                return language
        
        raise LanguageDetectionFailed(
            f"Could not detect language from extensions: {list(extension_counts.keys())}"
        )
    
    def create_adapter(self, language: str) -> BaseLanguageAdapter:
        """
        Create a language adapter for the specified language.
        
        Args:
            language: Language name (e.g., "python", "java")
            
        Returns:
            Language adapter instance
            
        Raises:
            LanguageNotSupported: If the language is not supported
        """
        adapter_class = self._adapters.get(language)
        if adapter_class is None:
            supported = list(self._adapters.keys())
            raise LanguageNotSupported(
                f"Language '{language}' is not supported. "
                f"Supported languages: {supported}",
                details={"language": language, "supported": supported},
            )
        
        return adapter_class()
    
    def detect_and_create(self, files: dict[str, str]) -> tuple[str, BaseLanguageAdapter]:
        """
        Detect language and create adapter in one step.
        
        Args:
            files: Dictionary mapping file paths to file contents
            
        Returns:
            Tuple of (language, adapter)
            
        Raises:
            LanguageDetectionFailed: If language cannot be detected
            LanguageNotSupported: If detected language is not supported
        """
        language = self.detect_language(files)
        adapter = self.create_adapter(language)
        return language, adapter
    
    def get_supported_languages(self) -> list[str]:
        """
        Get list of supported languages.
        
        Returns:
            List of supported language names
        """
        return list(self._adapters.keys())
    
    def is_language_supported(self, language: str) -> bool:
        """
        Check if a language is supported.
        
        Args:
            language: Language name to check
            
        Returns:
            True if supported, False otherwise
        """
        return language in self._adapters
    
    @staticmethod
    def _get_extension(file_path: str) -> str | None:
        """
        Get the file extension from a file path.
        
        Args:
            file_path: Path to the file
            
        Returns:
            File extension (e.g., ".py") or None
        """
        import os
        _, ext = os.path.splitext(file_path)
        return ext.lower() if ext else None


# Global factory instance
_factory: LanguageAdapterFactory | None = None


def get_language_factory() -> LanguageAdapterFactory:
    """
    Get the global language adapter factory.
    
    Returns:
        LanguageAdapterFactory instance
    """
    global _factory
    if _factory is None:
        _factory = LanguageAdapterFactory()
    return _factory
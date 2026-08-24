"""Language detection and adapter factory.

Simple language detection based on repository file extensions.
Returns the appropriate language adapter for compilation.
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from typing import TYPE_CHECKING

from core.errors import LanguageDetectionFailed, LanguageNotSupported
from engine.language.base import FileContext, LanguageSpec
from engine.language.builtins import create_default_language_registry
from engine.language.registry import LanguageRegistry

if TYPE_CHECKING:
    from engine.language.base import BaseLanguageAdapter


class LanguageDetector:
    """Determines which language a collection of repository files contains.

    Maintains separation of concerns by operating only on LanguageSpec metadata.
    """

    def __init__(self, registry: LanguageRegistry) -> None:
        """Initialize detector with a language registry."""
        self._registry = registry

    def detect(self, files: Iterable[FileContext]) -> LanguageSpec:
        """Detect the primary language from file contexts.

        Args:
            files: Iterable of FileContext objects.

        Returns:
            The detected LanguageSpec.

        Raises:
            LanguageDetectionFailed: If files list is empty or language cannot be detected.
        """
        votes: dict[LanguageSpec, int] = {}
        has_files = False

        for file in files:
            has_files = True
            matched_specs: set[LanguageSpec] = set()

            # 1. Match by language ID if present
            if file.language:
                try:
                    plugin = self._registry.get(file.language)
                    matched_specs.add(plugin.spec)
                except LanguageNotSupported:
                    pass

            # 2. Match by exact filename
            filename = os.path.basename(file.path)
            plugin_by_file = self._registry.find_by_filename(filename)
            if plugin_by_file:
                matched_specs.add(plugin_by_file.spec)

            # 3. Match by extension (case-insensitive)
            _, ext = os.path.splitext(file.path)
            plugin_by_ext = self._registry.find_by_extension(ext)
            if plugin_by_ext:
                matched_specs.add(plugin_by_ext.spec)

            # Accumulate votes
            for spec in matched_specs:
                votes[spec] = votes.get(spec, 0) + 1

        if not has_files:
            raise LanguageDetectionFailed("No files provided for language detection")

        if not votes:
            raise LanguageDetectionFailed(
                "Could not detect any registered language plugin for the provided files"
            )

        # Find the maximum vote count
        max_votes = max(votes.values())
        candidates = [spec for spec, v in votes.items() if v == max_votes]

        if len(candidates) == 1:
            return candidates[0]

        # In case of a tie, resolve using the registration/priority order in registry
        for spec in self._registry.specs():
            if spec in candidates:
                return spec

        return candidates[0]


class LanguageAdapterFactory:
    """Factory for creating language adapters based on repository content.

    Detects the primary language of a repository and returns the appropriate
    adapter for compilation.
    """

    def __init__(self, registry: LanguageRegistry | None = None) -> None:
        """Initialize the factory with a language registry."""
        self._registry = registry or get_default_registry()
        self._detector = LanguageDetector(self._registry)

    def detect_language(self, files: dict[str, str]) -> str:
        """Detect the primary language of a repository from its files.

        Args:
            files: Dictionary mapping file paths to file contents

        Returns:
            Detected language name (e.g., "python", "java")

        Raises:
            LanguageDetectionFailed: If language cannot be detected
        """
        if not files:
            raise LanguageDetectionFailed("No files provided for language detection")

        file_contexts = [
            FileContext(path=path, source=content, ast=None, language="")
            for path, content in files.items()
        ]
        spec = self._detector.detect(file_contexts)
        return spec.id

    def create_adapter(self, language: str) -> BaseLanguageAdapter:
        """Create a language adapter for the specified language.

        Args:
            language: Language name (e.g., "python", "java")

        Returns:
            Language adapter instance

        Raises:
            LanguageNotSupported: If the language is not supported
        """
        return self._registry.create_adapter(language)

    def detect_and_create(
        self, files: dict[str, str]
    ) -> tuple[str, BaseLanguageAdapter]:
        """Detect language and create adapter in one step.

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
        """Get list of supported languages.

        Returns:
            List of supported language names
        """
        return [spec.id for spec in self._registry.specs()]

    def is_language_supported(self, language: str) -> bool:
        """Check if a language is supported.

        Args:
            language: Language name to check

        Returns:
            True if supported, False otherwise
        """
        try:
            self._registry.get(language)
            return True
        except LanguageNotSupported:
            return False


# Global default registry and factory instances
_registry: LanguageRegistry | None = None
_factory: LanguageAdapterFactory | None = None


def get_default_registry() -> LanguageRegistry:
    """Get the global default language registry."""
    global _registry
    if _registry is None:
        _registry = create_default_language_registry()
    return _registry


def get_language_factory() -> LanguageAdapterFactory:
    """Get the global language adapter factory.

    Returns:
        LanguageAdapterFactory instance
    """
    global _factory
    if _factory is None:
        _factory = LanguageAdapterFactory(get_default_registry())
    return _factory

"""TypeScript language adapter implementation.

Provides compile and indexing stubs that raise LanguageNotSupported
as TypeScript analysis is a non-goal for this phase.
"""

from typing import Any
from core.errors import LanguageNotSupported
from engine.language.base import BaseLanguageAdapter
from engine.repository.model import RepositoryModel


class TypeScriptLanguageAdapter(BaseLanguageAdapter):
    """
    TypeScript language adapter.

    Acts as a stub that raises LanguageNotSupported on compilation / indexing actions
    since TypeScript analysis is a non-goal.
    """

    def __init__(self) -> None:
        """Initialize the adapter."""
        pass

    def get_language(self) -> str:
        """Get the language name this adapter handles.

        Returns:
            Language identifier: "typescript"
        """
        return "typescript"

    def get_compiler_passes(self) -> list[str]:
        """Get compiler passes.

        Returns:
            List of pass names in execution order (empty for typescript).
        """
        return []

    def compile(self, repository_input: dict[str, Any]) -> RepositoryModel:
        """Compile a typescript repository.

        Args:
            repository_input: Repository snapshot.

        Raises:
            LanguageNotSupported: Always, as typescript compilation is a non-goal.
        """
        raise LanguageNotSupported(
            "TypeScript language adapter is not supported.",
            details={"language": "typescript"},
        )

    def _index_single_file(self, file_path: str, content: str, language: str) -> Any:
        """Parse and run indexing passes on a single source file.

        Raises:
            LanguageNotSupported: Always, as typescript compilation is a non-goal.
        """
        raise LanguageNotSupported(
            "TypeScript language adapter is not supported.",
            details={"language": "typescript"},
        )

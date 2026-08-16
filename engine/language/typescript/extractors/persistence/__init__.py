"""TypeScript persistence extractor stub."""

from typing import Any
from engine.language.base import BaseExtractor


class TypeScriptPersistenceExtractor(BaseExtractor):
    """Stub extractor for TypeScript persistence."""

    def extract(self, tree: Any, file_path: str) -> list[dict[str, Any]]:
        return []

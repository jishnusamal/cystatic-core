"""TypeScript symbol extractor stub."""

from typing import Any

from engine.language.base import BaseExtractor


class TypeScriptSymbolExtractor(BaseExtractor):
    """Stub extractor for TypeScript symbols."""

    def extract(self, tree: Any, file_path: str) -> list[dict[str, Any]]:
        return []

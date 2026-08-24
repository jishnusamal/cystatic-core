"""TypeScript event extractor stub."""

from typing import Any

from engine.language.base import BaseExtractor


class TypeScriptEventExtractor(BaseExtractor):
    """Stub extractor for TypeScript events."""

    def extract(self, tree: Any, file_path: str) -> list[dict[str, Any]]:
        return []

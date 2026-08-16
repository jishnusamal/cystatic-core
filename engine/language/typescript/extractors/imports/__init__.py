"""TypeScript import extractor stub."""

from typing import Any
from engine.language.base import BaseExtractor


class TypeScriptImportExtractor(BaseExtractor):
    """Stub extractor for TypeScript imports."""

    def extract(self, tree: Any, file_path: str) -> list[dict[str, Any]]:
        return []

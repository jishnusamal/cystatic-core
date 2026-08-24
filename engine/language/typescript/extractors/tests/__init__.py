"""TypeScript test extractor stub."""

from typing import Any

from engine.language.base import BaseExtractor


class TypeScriptTestExtractor(BaseExtractor):
    """Stub extractor for TypeScript tests."""

    def extract(self, tree: Any, file_path: str) -> list[dict[str, Any]]:
        return []

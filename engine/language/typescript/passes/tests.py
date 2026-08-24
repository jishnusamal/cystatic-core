"""TypeScript test index pass stub."""

from typing import Any

from engine.language.base.file_context import FileContext
from engine.language.base.passes import BaseIndexPass


class TypeScriptTestIndexPass(BaseIndexPass):
    """Stub index pass for TypeScript tests."""

    def process(self, context: FileContext, builder: dict[str, Any]) -> None:
        pass

"""Java import index pass - extracts import statements from Java source.

Emits only raw import facts. No resolution, no symbol matching.
"""

import re
from typing import Any

from language_adapters.base.file_context import FileContext
from language_adapters.base.passes import BaseIndexPass
from language_adapters.model.repository_index import ImportEntry


class JavaImportIndexPass(BaseIndexPass):
    """Index pass that extracts import facts from Java source.

    Extracts: module path, imported names, import type, line number.
    No resolution of what the imports refer to - that's semantic compilation.
    """

    def process(self, context: FileContext, builder: dict[str, Any]) -> None:
        """Extract imports from a Java file context."""
        file_path = context.path
        content = '\n'.join(context.ast)

        import_pattern = r'import\s+(static\s+)?([\w.]+);'

        for match in re.finditer(import_pattern, content):
            is_static = match.group(1) is not None
            module = match.group(2)
            line = content[:match.start()].count('\n') + 1

            builder["imports"].append(
                ImportEntry(
                    module=module,
                    names=(module.split('.')[-1],),
                    import_type="from_import" if is_static else "import",
                    file=file_path,
                    line=line,
                )
            )
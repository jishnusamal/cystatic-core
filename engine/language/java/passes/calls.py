"""Java call index pass - extracts method calls from Java source.

Emits only raw call facts. No resolution, no graph construction.
"""

import re
from typing import Any

from language_adapters.base.file_context import FileContext
from language_adapters.base.passes import BaseIndexPass
from engine.repository.model.repository_index import CallEntry


class JavaCallIndexPass(BaseIndexPass):
    """Index pass that extracts call facts from Java source.

    Extracts: caller name, callee name, call type, line number.
    No resolution of what the callee refers to - that's semantic compilation.
    """

    def process(self, context: FileContext, builder: dict[str, Any]) -> None:
        """Extract calls from a Java file context."""
        lines = context.ast
        file_path = context.path

        call_pattern = r'(\w+)\.(\w+)\s*\('

        for i, line in enumerate(lines, 1):
            for match in re.finditer(call_pattern, line):
                caller_name = match.group(1)
                callee_name = match.group(2)

                # Skip common noise
                if callee_name in ('main', 'println', 'print'):
                    continue

                builder["calls"].append(
                    CallEntry(
                        caller=caller_name,
                        callee=callee_name,
                        call_type="direct",
                        file=file_path,
                        line=i,
                    )
                )
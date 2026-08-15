"""Python import index pass - extracts import statements from Python AST.

Emits only raw import facts. No resolution, no symbol matching.
"""

import ast
from typing import Any

from engine.language.base.file_context import FileContext
from engine.language.base.passes import BaseIndexPass
from engine.repository.model.repository_index import ImportEntry


class PythonImportIndexPass(BaseIndexPass):
    """Index pass that extracts import facts from Python AST.

    Extracts: module path, imported names, import type, line number.
    No resolution of what the imports refer to - that's semantic compilation.

    Supports both the visitor pattern (visit_Import, visit_ImportFrom)
    and the traditional process() method for backward compatibility.
    """

    def process(self, context: FileContext, builder: dict[str, Any]) -> None:
        """Extract imports from a Python file context (legacy mode)."""
        tree = context.ast
        file_path = context.path

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = node.module or "."
                names = [alias.name for alias in node.names]
                builder["imports"].append(
                    ImportEntry(
                        module=module,
                        names=tuple(names),
                        import_type="from_import",
                        file=file_path,
                        line=node.lineno,
                    )
                )
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    builder["imports"].append(
                        ImportEntry(
                            module=alias.name,
                            names=(alias.name,),
                            import_type="import",
                            file=file_path,
                            line=node.lineno,
                        )
                    )

    def visit_Import(
        self, node: ast.Import, context: FileContext, builder: dict[str, Any]
    ) -> None:
        """Handle import statement from visitor."""
        file_path = context.path
        for alias in node.names:
            builder["imports"].append(
                ImportEntry(
                    module=alias.name,
                    names=(alias.name,),
                    import_type="import",
                    file=file_path,
                    line=node.lineno,
                )
            )

    def visit_ImportFrom(
        self, node: ast.ImportFrom, context: FileContext, builder: dict[str, Any]
    ) -> None:
        """Handle from-import statement from visitor."""
        file_path = context.path
        module = node.module or "."
        names = [alias.name for alias in node.names]
        builder["imports"].append(
            ImportEntry(
                module=module,
                names=tuple(names),
                import_type="from_import",
                file=file_path,
                line=node.lineno,
            )
        )

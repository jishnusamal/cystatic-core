"""Java type relationship index pass - extracts inheritance, implementation, and composition.

Emits only raw type relationship facts. No resolution, no graph construction.
"""

import re
from typing import Any

from engine.language.base.file_context import FileContext
from engine.language.base.passes import BaseIndexPass
from engine.repository.model.repository_index import TypeRelationshipEntry


class JavaTypeIndexPass(BaseIndexPass):
    """Index pass that extracts type relationship facts from Java source.

    Extracts: source type, target type, relationship type, line number.
    No resolution of what types refer to - that's semantic compilation.
    """

    def process(self, context: FileContext, builder: dict[str, Any]) -> None:
        """Extract type relationships from a Java file context."""
        lines = context.ast
        file_path = context.path
        content = '\n'.join(lines)

        # Inheritance and implementation from class/interface/enum declarations
        class_pattern = (
            r'(?:public|private|protected)?\s*(?:abstract|final)?\s*'
            r'(?:class|interface|enum)\s+(\w+)'
            r'(?:\s+extends\s+(\w+(?:\.\w+)*))?'
            r'(?:\s+implements\s+([^{]+))?'
        )

        for match in re.finditer(class_pattern, content, re.MULTILINE):
            class_name = match.group(1)
            source = f"java://{file_path}#{class_name}"
            line = content[:match.start()].count('\n') + 1

            # Inheritance (extends)
            extends_name = match.group(2)
            if extends_name:
                builder["type_relationships"].append(
                    TypeRelationshipEntry(
                        source=source,
                        target=extends_name,
                        relation_type="extends",
                        file=file_path,
                        line=line,
                    )
                )

            # Interface implementation (implements)
            implements_names = match.group(3)
            if implements_names:
                for iface in re.split(r'\s*,\s*', implements_names.strip()):
                    iface = iface.strip()
                    if iface:
                        builder["type_relationships"].append(
                            TypeRelationshipEntry(
                                source=source,
                                target=iface,
                                relation_type="implements",
                                file=file_path,
                                line=line,
                            )
                        )

        # Composition from field declarations
        for i, line in enumerate(lines, 1):
            if self._is_inside_class(lines, i - 1):
                field_match = re.search(
                    r'(?:private|public|protected)?\s*(\w+(?:<[^>]+>)?)\s+(\w+)\s*;',
                    line,
                )
                if field_match:
                    field_type = field_match.group(1)
                    field_name = field_match.group(2)

                    # Skip primitives and common types
                    if field_type.lower() in (
                        'int', 'long', 'double', 'float', 'boolean',
                        'string', 'void', 'byte', 'short', 'char',
                    ):
                        continue

                    class_name = self._find_enclosing_class(lines, i - 1)
                    if class_name:
                        source = f"java://{file_path}#{class_name}"
                        builder["type_relationships"].append(
                            TypeRelationshipEntry(
                                source=source,
                                target=field_type,
                                relation_type="composes",
                                file=file_path,
                                line=i,
                                metadata={'field': field_name},
                            )
                        )

    def _is_inside_class(self, lines: list[str], line_idx: int) -> bool:
        """Check if a line is inside a class definition."""
        if line_idx < 0 or line_idx >= len(lines):
            return False
        open_braces = 0
        for i in range(line_idx):
            line = lines[i]
            open_braces += line.count('{') - line.count('}')
        return open_braces > 0

    def _find_enclosing_class(self, lines: list[str], line_idx: int) -> str | None:
        """Find the name of the class enclosing a line."""
        class_pattern = r'(?:public|private|protected)?\s*(?:abstract|final)?\s*class\s+(\w+)'
        for i in range(line_idx, -1, -1):
            match = re.search(class_pattern, lines[i])
            if match:
                # Check if the line is inside this class
                brace_count = 0
                for j in range(i, line_idx):
                    brace_count += lines[j].count('{') - lines[j].count('}')
                if brace_count > 0:
                    return match.group(1)
        return None
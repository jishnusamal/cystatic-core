"""Java symbol index pass - extracts symbols from Java source.

Only emits structural facts: class, method, function names, lines, visibility.
No semantic inference, no reference resolution.
"""

import re
from typing import Any

from engine.language.base.file_context import FileContext
from engine.language.base.passes import BaseIndexPass
from engine.repository.model.repository_index import SymbolEntry


class JavaSymbolIndexPass(BaseIndexPass):
    """Index pass that extracts symbol facts from Java source.

    Extracts: classes, methods, functions with their names, lines, visibility.
    No semantic interpretation - just structural symbol discovery.
    """

    def process(self, context: FileContext, builder: dict[str, Any]) -> None:
        """Extract symbols from a Java file context."""
        lines = context.ast
        file_path = context.path
        content = '\n'.join(lines)

        # Extract classes
        for cls in self._extract_classes(content, lines, file_path):
            builder["symbols"].append(cls)

        # Extract top-level functions (methods not in classes)
        for func in self._extract_functions(content, lines, file_path):
            builder["symbols"].append(func)

    def _extract_classes(
        self,
        content: str,
        lines: list[str],
        file_path: str,
    ) -> list[SymbolEntry]:
        """Extract class definitions with their methods."""
        classes: list[SymbolEntry] = []
        class_pattern = r'(public|private|protected)?\s*(abstract|final)?\s*class\s+(\w+)'

        for i, line in enumerate(lines, 1):
            match = re.search(class_pattern, line)
            if match:
                visibility = self._parse_visibility(match.group(1))
                class_name = match.group(3)
                end_line = self._find_block_end(lines, i - 1)

                methods = self._extract_methods_from_block(lines, i - 1, end_line)

                properties: dict[str, Any] = {}
                if '@Entity' in content:
                    properties['is_entity'] = True
                if '@RestController' in content or '@Controller' in content:
                    properties['is_controller'] = True

                class_sym = SymbolEntry(
                    name=class_name,
                    kind="class",
                    file=file_path,
                    start_line=i,
                    end_line=end_line,
                    visibility=visibility,
                    properties=properties,
                )
                classes.append(class_sym)

                # Add methods as separate symbols with parent class
                for method in methods:
                    method_with_parent = SymbolEntry(
                        name=method.name,
                        kind=method.kind,
                        file=file_path,
                        start_line=method.start_line,
                        end_line=method.end_line,
                        visibility=method.visibility,
                        parent=class_name,
                        properties=method.properties,
                    )
                    classes.append(method_with_parent)

        return classes

    def _extract_functions(
        self,
        content: str,
        lines: list[str],
        file_path: str,
    ) -> list[SymbolEntry]:
        """Extract top-level functions (methods not in classes)."""
        functions: list[SymbolEntry] = []
        method_pattern = r'(public|private|protected)?\s*(static)?\s*\w+\s+(\w+)\s*\('

        for i, line in enumerate(lines, 1):
            if self._is_inside_class(lines, i - 1):
                continue

            match = re.search(method_pattern, line)
            if match and 'class ' not in line:
                visibility = self._parse_visibility(match.group(1))
                func_name = match.group(3)
                end_line = self._find_block_end(lines, i - 1)

                functions.append(SymbolEntry(
                    name=func_name,
                    kind="function",
                    file=file_path,
                    start_line=i,
                    end_line=end_line,
                    visibility=visibility,
                ))

        return functions

    def _extract_methods_from_block(
        self,
        lines: list[str],
        start_idx: int,
        end_idx: int,
    ) -> list[SymbolEntry]:
        """Extract methods from a class block.

        Returns SymbolEntry objects without parent or file set.
        Parent and file are set by the caller when adding to results.
        """
        methods: list[SymbolEntry] = []
        method_pattern = r'(public|private|protected)?\s*(static)?\s*\w+\s+(\w+)\s*\('

        for i in range(start_idx, min(end_idx, len(lines))):
            line = lines[i]
            match = re.search(method_pattern, line)
            if match and 'class ' not in line and 'interface ' not in line:
                visibility = self._parse_visibility(match.group(1))
                method_name = match.group(3)
                method_end = self._find_block_end(lines, i)

                methods.append(SymbolEntry(
                    name=method_name,
                    kind="method",
                    file="",
                    start_line=i + 1,
                    end_line=method_end,
                    visibility=visibility,
                ))

        return methods

    def _parse_visibility(self, visibility_str: str | None) -> str:
        """Parse Java visibility modifier."""
        return visibility_str or 'public'

    def _is_inside_class(self, lines: list[str], line_idx: int) -> bool:
        """Check if a line is inside a class definition."""
        if line_idx < 0 or line_idx >= len(lines):
            return False

        open_braces = 0
        for i in range(line_idx):
            line = lines[i]
            open_braces += line.count('{') - line.count('}')

        return open_braces > 0

    def _find_block_end(self, lines: list[str], start_idx: int) -> int:
        """Find the end line of a code block."""
        brace_count = 0
        found_open = False

        for i in range(start_idx, len(lines)):
            line = lines[i]

            if not found_open:
                if '{' in line:
                    found_open = True
                    brace_count = 1
            else:
                brace_count += line.count('{') - line.count('}')

                if brace_count <= 0:
                    return i + 1

        return min(start_idx + 10, len(lines))
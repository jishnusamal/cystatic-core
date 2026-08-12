"""Java test index pass - discovers test classes, methods, and fixtures.

Emits only structural test facts. No resolution, no graph construction.
"""

import re
from typing import Any

from engine.language.base.file_context import FileContext
from engine.language.base.passes import BaseIndexPass
from engine.repository.model.repository_index import TestEntry


class JavaTestIndexPass(BaseIndexPass):
    """Index pass that extracts test facts from Java source.

    Extracts: test classes, test methods, framework, assertions, fixtures.
    No semantic interpretation - just structural test discovery.
    """

    ASSERTION_METHODS = {
        'assertEquals', 'assertNotEquals', 'assertTrue', 'assertFalse',
        'assertNull', 'assertNotNull', 'assertSame', 'assertNotSame',
        'assertThat', 'assertThrows', 'assertDoesNotThrow',
        'assertArrayEquals', 'assertIterableEquals',
        'verify', 'assertTimeout', 'assertAll',
    }

    def process(self, context: FileContext, builder: dict[str, Any]) -> None:
        """Extract test definitions from a Java file context."""
        lines = context.ast
        file_path = context.path
        content = '\n'.join(lines)

        class_pattern = r'(?:public\s+)?class\s+(\w+)'
        for class_match in re.finditer(class_pattern, content):
            class_name = class_match.group(1)

            if not self._is_test_class(content, class_match.start()):
                continue

            class_line = content[:class_match.start()].count('\n') + 1

            test_methods: list[TestEntry] = []
            in_class = False
            brace_depth = 0

            for i, line in enumerate(lines):
                if not in_class:
                    if i >= class_line - 1:
                        brace_depth += line.count('{') - line.count('}')
                        if line.count('{') > 0:
                            in_class = True
                    continue

                brace_depth += line.count('{') - line.count('}')
                if brace_depth <= 0:
                    break

                # Check for test method annotations
                if self._has_test_annotation(line) and len(lines) > i + 1:
                    next_line = lines[i + 1]
                    method_match = re.search(
                        r'(?:public|private|protected)?\s*(?:\w+)\s+(\w+)\s*\(',
                        next_line,
                    )
                    if method_match:
                        method_name = method_match.group(1)
                        assertions = self._find_assertions(lines, i + 1)

                        test_methods.append(TestEntry(
                            name=method_name,
                            kind="method",
                            framework=self._detect_test_framework(content),
                            file=file_path,
                            line=i + 2,
                            assertions=tuple(assertions),
                        ))

            builder["tests"].append(TestEntry(
                name=class_name,
                kind="class",
                framework=self._detect_test_framework(content),
                file=file_path,
                line=class_line,
                test_methods=tuple(test_methods),
            ))

    def _is_test_class(self, content: str, class_pos: int) -> bool:
        """Check if a class is a test class."""
        if '@RunWith' in content or '@ExtendWith' in content:
            return True

        class_block = content[class_pos:class_pos + 200]
        if re.search(r'class\s+\w+Test', class_block):
            return True

        for annotation in ['@Test', '@Before', '@After', '@BeforeEach', '@AfterEach']:
            if annotation in content[class_pos:class_pos + 1000]:
                return True

        return False

    def _has_test_annotation(self, line: str) -> bool:
        """Check if a line contains a test annotation."""
        line = line.strip()
        return line in ('@Test', '@ParameterizedTest')

    def _detect_test_framework(self, content: str) -> str:
        """Detect the test framework used."""
        if '@BeforeEach' in content or '@AfterEach' in content or '@ExtendWith' in content:
            return 'junit5'
        if '@Test' in content or '@Before' in content:
            return 'junit'
        if 'TestNG' in content or '@BeforeSuite' in content:
            return 'testng'
        return 'junit'

    def _find_assertions(self, lines: list[str], start_idx: int) -> list[str]:
        """Find assertion methods in a test method."""
        assertions: set[str] = set()
        brace_depth = 0
        for i in range(start_idx, min(start_idx + 50, len(lines))):
            line = lines[i]
            brace_depth += line.count('{') - line.count('}')
            if brace_depth < 0:
                break

            for assertion in self.ASSERTION_METHODS:
                if assertion in line:
                    assertions.add(assertion)

        return list(assertions)
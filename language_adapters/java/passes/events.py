"""Java event index pass - detects event publish, emit, dispatch, and send operations.

Emits only structural event facts. No resolution, no graph construction.
"""

import re
from typing import Any

from language_adapters.base.file_context import FileContext
from language_adapters.base.passes import BaseIndexPass
from language_adapters.model.repository_index import EventEntry


class JavaEventIndexPass(BaseIndexPass):
    """Index pass that extracts event facts from Java source.

    Extracts: event operation kind, event name, framework, line number.
    No resolution of what symbols are involved - that's semantic compilation.
    """

    EVENT_PATTERNS = [
        (r'(\w+)\.publishEvent\s*\(', 'publish', 'spring'),
        (r'(\w+)\.send\s*\(', 'send', 'generic'),
        (r'(\w+)\.convertAndSend\s*\(', 'send', 'spring'),
        (r'(\w+)\.publish\s*\(', 'publish', 'generic'),
        (r'(\w+)\.emit\s*\(', 'emit', 'generic'),
        (r'(\w+)\.dispatch\s*\(', 'dispatch', 'generic'),
        (r'(\w+)\.broadcast\s*\(', 'broadcast', 'generic'),
        (r'(\w+)\.trigger\s*\(', 'dispatch', 'generic'),
    ]

    FRAMEWORK_DETECT = {
        'kafkaTemplate': 'kafka',
        'rabbitTemplate': 'rabbitmq',
        'jmsTemplate': 'jms',
        'eventPublisher': 'spring',
        'applicationEventPublisher': 'spring',
        'producer': 'kafka',
    }

    def process(self, context: FileContext, builder: dict[str, Any]) -> None:
        """Extract event operations from a Java file context."""
        lines = context.ast
        file_path = context.path

        for i, line in enumerate(lines, 1):
            for pattern, operation_kind, default_framework in self.EVENT_PATTERNS:
                for match in re.finditer(pattern, line):
                    object_name = match.group(1)
                    caller_name = self._find_caller_method(lines, i - 1)
                    framework = self.FRAMEWORK_DETECT.get(object_name, default_framework)
                    event_name = self._extract_event_name(line)

                    builder["events"].append(
                        EventEntry(
                            symbol_name=caller_name or "unknown",
                            operation_kind=operation_kind,
                            event_name=event_name,
                            framework=framework,
                            file=file_path,
                            line=i,
                        )
                    )

    def _extract_event_name(self, line: str) -> str:
        """Extract the event name/type from a line."""
        string_match = re.search(r'\(\s*"([^"]+)"', line)
        if string_match:
            return string_match.group(1)

        class_match = re.search(r'\(\s*(\w+)\.class', line)
        if class_match:
            return class_match.group(1)

        return ''

    def _find_caller_method(self, lines: list[str], line_idx: int) -> str | None:
        """Find the method enclosing a line."""
        method_pattern = r'(?:public|private|protected)?\s*(?:\w+)\s+(\w+)\s*\('
        for i in range(line_idx, -1, -1):
            match = re.search(method_pattern, lines[i])
            if match and 'class ' not in lines[i] and 'interface ' not in lines[i]:
                return match.group(1)
        return None
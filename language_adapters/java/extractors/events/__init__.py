"""Java event extractor - detects event publish, emit, dispatch, and send operations."""

import re
from typing import Any

from language_adapters.base import BaseExtractor


class JavaEventExtractor(BaseExtractor):
    """
    Extracts event operations from Java source files.

    Recognizes framework-specific event patterns:
    - Spring ApplicationEventPublisher: publishEvent()
    - Kafka: kafkaTemplate.send()
    - JMS: jmsTemplate.convertAndSend()
    - RabbitMQ: rabbitTemplate.convertAndSend()
    - Generic patterns: publish(), emit(), dispatch(), send()

    Produces a list of dicts with keys: symbol_id, operation_kind, event_name,
    framework, file, line.
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

    def extract(self, tree: list[str], file_path: str) -> list[dict[str, Any]]:
        """
        Extract event operations from a Java source file.

        Args:
            tree: List of lines from the source file
            file_path: Path to the source file

        Returns:
            List of event construct dicts
        """
        events = []

        for i, line in enumerate(tree, 1):
            for pattern, operation_kind, default_framework in self.EVENT_PATTERNS:
                for match in re.finditer(pattern, line):
                    object_name = match.group(1)
                    caller_id = self._find_caller_method(tree, i - 1, file_path)
                    framework = self.FRAMEWORK_DETECT.get(object_name, default_framework)
                    event_name = self._extract_event_name(line)

                    events.append({
                        'symbol_id': caller_id or '',
                        'operation_kind': operation_kind,
                        'event_name': event_name,
                        'framework': framework,
                        'file': file_path,
                        'line': i,
                    })

        return events

    def _extract_event_name(self, line: str) -> str:
        """Extract the event name/type from a line."""
        # Look for string argument in the call
        string_match = re.search(r'\(\s*"([^"]+)"', line)
        if string_match:
            return string_match.group(1)

        # Look for class reference argument
        class_match = re.search(r'\(\s*(\w+)\.class', line)
        if class_match:
            return class_match.group(1)

        return ''

    def _find_caller_method(self, lines: list[str], line_idx: int, file_path: str) -> str | None:
        """Find the method enclosing a line."""
        method_pattern = r'(?:public|private|protected)?\s*(?:\w+)\s+(\w+)\s*\('
        for i in range(line_idx, -1, -1):
            match = re.search(method_pattern, lines[i])
            if match and 'class ' not in lines[i] and 'interface ' not in lines[i]:
                return f"java://{file_path}::{match.group(1)}"
        return None
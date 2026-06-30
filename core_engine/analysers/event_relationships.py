"""
Event Relationship Analyzer

Discovers asynchronous relationships.
Produces: Publishes Event, Consumes Event, Shared Topic, Shared Queue
"""
from __future__ import annotations

from typing import Any
from core_engine.analysers.base import EvidenceAnalyzer, AnalyzerOutput
from core_engine.analysers.analysis_context import AnalysisContext


class EventRelationshipAnalyzer(EvidenceAnalyzer):
    """Discover asynchronous relationships.
    
    This analyzer:
    - Identifies event publishing patterns
    - Identifies event consumption patterns
    - Detects shared topics/queues
    - Never predicts failures
    - Only extracts deterministic event relationship facts
    """
    
    # Event publishing patterns
    PUBLISH_PATTERNS = (
        "publish(", "send(", "emit(", "produce(",
        ".publish(", ".send(", ".emit(", ".produce(",
        "event_bus.publish", "message_bus.send",
        "kafka.produce", "rabbitmq.publish",
        "sqs.send_message", "pubsub.publish",
    )
    
    # Event consumption patterns
    CONSUME_PATTERNS = (
        "consume(", "receive(", "listen(", "subscribe(",
        ".consume(", ".receive(", ".listen(", ".subscribe(",
        "event_bus.subscribe", "message_bus.receive",
        "kafka.consume", "rabbitmq.consume",
        "sqs.receive_message", "pubsub.subscribe",
    )
    
    # Topic/queue name patterns
    TOPIC_PATTERNS = (
        "topic", "queue", "channel", "stream",
        "events.", "messages.", "events/", "messages/",
    )
    
    def analyze(self, context: AnalysisContext) -> AnalyzerOutput:
        """Extract event relationships from the analysis context.
        
        Args:
            context: AnalysisContext containing enriched_files with hunks.
            
        Returns:
            AnalyzerOutput with impact_evidence for event relationships.
        """
        output = AnalyzerOutput()
        
        # Track events published/consumed by each changed symbol
        published_events: dict[str, list[str]] = {}
        consumed_events: dict[str, list[str]] = {}
        
        # Extract from enriched_files
        for file_data in context.enriched_files:
            file_path = file_data.get("file_path", "")
            changed_functions = file_data.get("changed_functions", [])
            hunks = file_data.get("hunks", [])
            
            # Get added lines
            added_lines = self._extract_added_lines(hunks)
            
            # For each changed function, detect event operations
            for func in changed_functions:
                func_name = self._get_func_name(func)
                if not func_name:
                    continue
                
                symbol_key = f"{file_path}:{func_name}"
                published = []
                consumed = []
                
                # Check added lines for event operations
                for line in added_lines:
                    line_lower = line.lower()
                    
                    # Check for publishing
                    if self._matches_any(line_lower, self.PUBLISH_PATTERNS):
                        event_name = self._extract_event_name(line, "publish")
                        if event_name:
                            published.append(event_name)
                    
                    # Check for consumption
                    if self._matches_any(line_lower, self.CONSUME_PATTERNS):
                        event_name = self._extract_event_name(line, "consume")
                        if event_name:
                            consumed.append(event_name)
                    
                    # Check for topic/queue references
                    if self._matches_any(line_lower, self.TOPIC_PATTERNS):
                        topic_name = self._extract_topic_name(line)
                        if topic_name:
                            # Could be either publish or consume
                            published.append(topic_name)
                            consumed.append(topic_name)
                
                if published:
                    published_events[symbol_key] = list(set(published))
                if consumed:
                    consumed_events[symbol_key] = list(set(consumed))
        
        # Generate impact evidence for event relationships
        
        # 1. Symbols that publish the same event
        all_publishers = list(published_events.keys())
        for i, pub1 in enumerate(all_publishers):
            for pub2 in all_publishers[i+1:]:
                events1 = set(published_events[pub1])
                events2 = set(published_events[pub2])
                shared_events = events1.intersection(events2)
                
                if shared_events:
                    output.impact_evidence.append({
                        "source_symbol": pub1,
                        "target_symbol": pub2,
                        "evidence_type": "shared_event_publication",
                        "confidence": 0.7,
                        "explanation": f"Both symbols publish to shared events: {', '.join(shared_events)}",
                        "metadata": {
                            "shared_events": list(shared_events),
                        },
                    })
        
        # 2. Symbols that consume the same event
        all_consumers = list(consumed_events.keys())
        for i, con1 in enumerate(all_consumers):
            for con2 in all_consumers[i+1:]:
                events1 = set(consumed_events[con1])
                events2 = set(consumed_events[con2])
                shared_events = events1.intersection(events2)
                
                if shared_events:
                    output.impact_evidence.append({
                        "source_symbol": con1,
                        "target_symbol": con2,
                        "evidence_type": "shared_event_consumption",
                        "confidence": 0.7,
                        "explanation": f"Both symbols consume from shared events: {', '.join(shared_events)}",
                        "metadata": {
                            "shared_events": list(shared_events),
                        },
                    })
        
        # 3. Publisher-consumer relationships
        for pub_key, pub_events in published_events.items():
            for con_key, con_events in consumed_events.items():
                shared_events = set(pub_events).intersection(set(con_events))
                if shared_events:
                    output.impact_evidence.append({
                        "source_symbol": pub_key,
                        "target_symbol": con_key,
                        "evidence_type": "event_publication_consumption",
                        "confidence": 0.8,
                        "explanation": f"Publisher-consumer relationship via events: {', '.join(shared_events)}",
                        "metadata": {
                            "shared_events": list(shared_events),
                        },
                    })
        
        return output
    
    def _extract_added_lines(self, hunks: list[Any]) -> list[str]:
        """Extract added lines from hunks."""
        added_lines = []
        
        for hunk in hunks:
            hunk_dict = self._to_dict(hunk)
            lines = hunk_dict.get("lines", [])
            
            for line in lines:
                line_dict = self._to_dict(line)
                if line_dict.get("line_type") == "added":
                    content = str(line_dict.get("content", ""))
                    if content.strip():
                        added_lines.append(content)
        
        return added_lines
    
    def _extract_event_name(self, line: str, operation: str) -> str | None:
        """Extract event name from a line."""
        # Look for quoted strings or identifiers after the operation
        import re
        
        # Pattern for event names in quotes
        quote_pattern = rf'{operation}\s*["\']([^"\']+)["\']'
        match = re.search(quote_pattern, line, re.IGNORECASE)
        if match:
            return match.group(1)
        
        # Pattern for event names without quotes (identifiers)
        identifier_pattern = rf'{operation}\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*[,(]'
        match = re.search(identifier_pattern, line, re.IGNORECASE)
        if match:
            return match.group(1)
        
        return None
    
    def _extract_topic_name(self, line: str) -> str | None:
        """Extract topic/queue name from a line."""
        import re
        
        # Look for topic/queue names
        patterns = [
            r'topic[:\s]+["\']?([^"\')\s]+)',
            r'queue[:\s]+["\']?([^"\')\s]+)',
            r'channel[:\s]+["\']?([^"\')\s]+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, line, re.IGNORECASE)
            if match:
                return match.group(1)
        
        return None
    
    def _matches_any(self, text: str, patterns: tuple[str, ...]) -> bool:
        """Check if text matches any of the patterns."""
        return any(pattern in text for pattern in patterns)
    
    def _get_func_name(self, func: Any) -> str:
        """Extract function name from function object."""
        if isinstance(func, dict):
            return func.get("name", "")
        if hasattr(func, "model_dump"):
            return func.model_dump().get("name", "")
        if hasattr(func, "name"):
            return func.name
        return ""
    
    def _to_dict(self, value: Any) -> dict[str, Any]:
        """Convert value to dict."""
        if isinstance(value, dict):
            return value
        if hasattr(value, "model_dump"):
            return value.model_dump()
        return {}
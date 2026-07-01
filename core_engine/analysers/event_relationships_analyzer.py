"""
Event Relationship Analyzer

Extracts event-driven relationships and message flows.
This enables reasoning across asynchronous workflows.

Produces evidence types:
- publishes_event
- consumes_event
- shared_event
"""
from __future__ import annotations

from typing import Any
from core_engine.analysers.base import EvidenceAnalyzer, AnalyzerOutput
from core_engine.analysers.analysis_context import AnalysisContext
from core_engine.models.enums import EvidenceType


class EventRelationshipAnalyzer(EvidenceAnalyzer):
    """Extract event-driven relationships and message flows.
    
    This analyzer:
    - Identifies event publishers and consumers
    - Detects message queue patterns
    - Maps event flows across services
    - Never predicts failures
    - Only extracts deterministic event facts
    """
    
    # Event patterns to detect
    EVENT_PATTERNS = {
        # Event publishing
        "publish_patterns": [
            "publish(",
            "emit(",
            "send_event(",
            "dispatch(",
            "produce(",
            "event_bus.publish",
            "kafka.producer",
            "rabbitmq.publish",
        ],
        # Event consumption
        "consume_patterns": [
            "subscribe(",
            "consume(",
            "on_event(",
            "handle_event(",
            "receive(",
            "event_bus.subscribe",
            "kafka.consumer",
            "rabbitmq.consume",
        ],
        # Event definitions
        "event_definitions": [
            "class.*Event",
            "Event(",
            "event_type",
            "event_name",
        ],
    }
    
    # Common event naming patterns
    EVENT_NAME_PATTERNS = [
        r"(\w+Event)",
        r"(\w+Completed)",
        r"(\w+Created)",
        r"(\w+Updated)",
        r"(\w+Deleted)",
        r"(\w+Failed)",
        r"(\w+Started)",
    ]
    
    def analyze(self, context: AnalysisContext) -> AnalyzerOutput:
        """Extract event relationships from the analysis context.
        
        Args:
            context: AnalysisContext containing enriched_files and changed functions.
            
        Returns:
            AnalyzerOutput with event relationship evidence.
        """
        output = AnalyzerOutput()
        
        # Track events and their publishers/consumers
        events: dict[str, dict[str, list[str]]] = {}  # event_name -> {"publishers": [...], "consumers": [...]}
        
        # Extract from enriched files
        for file_data in context.enriched_files:
            file_path = file_data.get("file_path", "")
            changed_functions = file_data.get("changed_functions", [])
            keyword_signals = file_data.get("keyword_signals", [])
            
            # Check changed functions for event patterns
            for func in changed_functions:
                func_name = self._get_func_name(func)
                if not func_name:
                    continue
                
                func_text = self._get_func_text(func)
                
                # Detect event operations
                event_ops = self._detect_event_operations(func_text, keyword_signals)
                
                for event_name, operations in event_ops.items():
                    if event_name not in events:
                        events[event_name] = {"publishers": [], "consumers": []}
                    
                    # Add evidence for each operation
                    if "publishes" in operations:
                        events[event_name]["publishers"].append(func_name)
                        output.impact_evidence.append({
                            "source_symbol": func_name,
                            "target_symbol": event_name,
                            "evidence_type": "publishes_event",
                            "confidence": 0.85,
                            "explanation": f"Function {func_name} publishes {event_name} event",
                            "metadata": {
                                "file_path": file_path,
                                "event_name": event_name,
                                "operation": "publish",
                            },
                        })
                    
                    if "consumes" in operations:
                        events[event_name]["consumers"].append(func_name)
                        output.impact_evidence.append({
                            "source_symbol": func_name,
                            "target_symbol": event_name,
                            "evidence_type": "consumes_event",
                            "confidence": 0.85,
                            "explanation": f"Function {func_name} consumes {event_name} event",
                            "metadata": {
                                "file_path": file_path,
                                "event_name": event_name,
                                "operation": "consume",
                            },
                        })
            
            # Check keyword signals for event hints
            for signal in keyword_signals:
                signal_text = signal.keyword if hasattr(signal, "keyword") else str(signal)
                events_found = self._extract_event_names(signal_text)
                
                for event_name in events_found:
                    if event_name not in events:
                        events[event_name] = {"publishers": [], "consumers": []}
                    
                    output.impact_evidence.append({
                        "source_symbol": file_path,
                        "target_symbol": event_name,
                        "evidence_type": "shared_event",
                        "confidence": 0.6,
                        "explanation": f"Keyword signal suggests {event_name} event",
                        "metadata": {
                            "keyword": signal_text,
                            "file_path": file_path,
                        },
                    })
        
        # Generate shared event evidence
        # If multiple functions publish/consume the same event, they're connected
        for event_name, participants in events.items():
            publishers = participants["publishers"]
            consumers = participants["consumers"]
            all_functions = publishers + consumers
            
            if len(all_functions) > 1:
                # Connect publishers to consumers
                for pub in publishers:
                    for con in consumers:
                        output.impact_evidence.append({
                            "source_symbol": pub,
                            "target_symbol": con,
                            "evidence_type": "shared_event",
                            "confidence": 0.8,
                            "explanation": f"{pub} publishes {event_name} event consumed by {con}",
                            "metadata": {
                                "event_name": event_name,
                                "pub_role": "publisher",
                                "con_role": "consumer",
                            },
                        })
                
                # Connect multiple publishers
                if len(publishers) > 1:
                    for i, pub1 in enumerate(publishers):
                        for pub2 in publishers[i+1:]:
                            output.impact_evidence.append({
                                "source_symbol": pub1,
                                "target_symbol": pub2,
                                "evidence_type": "shared_event",
                                "confidence": 0.7,
                                "explanation": f"Both publish {event_name} event",
                                "metadata": {
                                    "event_name": event_name,
                                    "role": "publisher",
                                },
                            })
                
                # Connect multiple consumers
                if len(consumers) > 1:
                    for i, con1 in enumerate(consumers):
                        for con2 in consumers[i+1:]:
                            output.impact_evidence.append({
                                "source_symbol": con1,
                                "target_symbol": con2,
                                "evidence_type": "shared_event",
                                "confidence": 0.7,
                                "explanation": f"Both consume {event_name} event",
                                "metadata": {
                                    "event_name": event_name,
                                    "role": "consumer",
                                },
                            })
        
        return output
    
    def _detect_event_operations(self, func_text: str, keyword_signals: list) -> dict[str, list[str]]:
        """Detect event operations in function text.
        
        Args:
            func_text: Function source code or metadata
            keyword_signals: List of keyword signals from analysis
            
        Returns:
            Dictionary mapping event names to list of operations ("publishes", "consumes")
        """
        event_operations: dict[str, list[str]] = {}
        text_lower = func_text.lower() if func_text else ""
        
        # Detect event names
        event_names = self._extract_event_names(func_text)
        
        if not event_names:
            return event_operations
        
        # Detect publish operations
        for pattern in self.EVENT_PATTERNS["publish_patterns"]:
            if pattern.lower() in text_lower:
                for event_name in event_names:
                    if event_name not in event_operations:
                        event_operations[event_name] = []
                    if "publishes" not in event_operations[event_name]:
                        event_operations[event_name].append("publishes")
                break
        
        # Detect consume operations
        for pattern in self.EVENT_PATTERNS["consume_patterns"]:
            if pattern.lower() in text_lower:
                for event_name in event_names:
                    if event_name not in event_operations:
                        event_operations[event_name] = []
                    if "consumes" not in event_operations[event_name]:
                        event_operations[event_name].append("consumes")
                break
        
        # Check keyword signals for additional hints
        for signal in keyword_signals:
            signal_text = signal.keyword if hasattr(signal, "keyword") else str(signal)
            signal_lower = signal_text.lower()
            
            if any(pp.lower() in signal_lower for pp in self.EVENT_PATTERNS["publish_patterns"]):
                for event_name in event_names:
                    if event_name not in event_operations:
                        event_operations[event_name] = []
                    if "publishes" not in event_operations[event_name]:
                        event_operations[event_name].append("publishes")
            
            if any(cp.lower() in signal_lower for cp in self.EVENT_PATTERNS["consume_patterns"]):
                for event_name in event_names:
                    if event_name not in event_operations:
                        event_operations[event_name] = []
                    if "consumes" not in event_operations[event_name]:
                        event_operations[event_name].append("consumes")
        
        return event_operations
    
    def _extract_event_names(self, text: str) -> list[str]:
        """Extract event names from text.
        
        Args:
            text: Text to analyze
            
        Returns:
            List of event names detected
        """
        if not text:
            return []
        
        import re
        event_names = []
        
        # Look for event naming patterns
        for pattern in self.EVENT_NAME_PATTERNS:
            matches = re.findall(pattern, text)
            event_names.extend(matches)
        
        # Deduplicate
        event_names = list(set(event_names))
        
        return event_names
    
    def _get_func_name(self, func: Any) -> str:
        """Extract function name from function object."""
        if isinstance(func, dict):
            return func.get("name", "")
        if hasattr(func, "model_dump"):
            return func.model_dump().get("name", "")
        if hasattr(func, "name"):
            return func.name
        return ""
    
    def _get_func_text(self, func: Any) -> str:
        """Extract function text/code from function object."""
        if isinstance(func, dict):
            return func.get("text", "") or func.get("code", "") or func.get("name", "")
        if hasattr(func, "model_dump"):
            dump = func.model_dump()
            return dump.get("text", "") or dump.get("code", "") or dump.get("name", "")
        if hasattr(func, "text"):
            return func.text
        if hasattr(func, "code"):
            return func.code
        if hasattr(func, "name"):
            return func.name
        return ""
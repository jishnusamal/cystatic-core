"""
Side Effect Analyzer

Extracts observable system interactions from the change.
Produces: Database writes/reads, Cache operations, HTTP calls, Queue publishing/consumption, File IO, External APIs
"""
from __future__ import annotations

from typing import Any
from core_engine.analysers.base import EvidenceAnalyzer, AnalyzerOutput
from core_engine.analysers.analysis_context import AnalysisContext


class SideEffectAnalyzer(EvidenceAnalyzer):
    """Extract observable system interactions from the change.
    
    This analyzer:
    - Detects database operations (reads/writes)
    - Detects cache operations
    - Detects HTTP calls
    - Detects queue publishing/consumption
    - Detects file IO
    - Detects external API calls
    - Never performs business reasoning
    - Only extracts language-level facts
    """
    
    # Patterns for detecting side effects
    DATABASE_WRITE_PATTERNS = (
        "save(", "update(", "insert(", "delete(", "commit(",
        ".save(", ".update(", ".insert(", ".delete(",
        "session.commit(", "session.add(", "session.delete(",
        "db.commit(", "db.add(", "db.delete(",
        "transaction.commit(", "transaction.rollback(",
    )
    
    DATABASE_READ_PATTERNS = (
        "query(", "filter(", "get(", "find(", "select ",
        ".query(", ".filter(", ".get(", ".find(",
        "session.query(", "db.query(",
    )
    
    CACHE_PATTERNS = (
        "redis.", "cache.set", "memcache.", "cache.set(",
        "cache.add(", "cache.put ", "cache.replace(",
        ".set(", ".add(", ".put(", ".replace(",
        "cache_client.set(", "memcached.set(",
    )
    
    HTTP_CALL_PATTERNS = (
        "requests.", "httpx.", "http.client", "urllib.request",
        "aiohttp.", "urllib3.", "fetch(", "axios.",
        "stripe.", "twilio.", "sendgrid.", "mailgun.",
    )
    
    QUEUE_PUBLISH_PATTERNS = (
        "publish(", "send(", "enqueue(", "produce(",
        ".publish(", ".send(", ".enqueue(", ".produce(",
        "queue.put(", "channel.basic_publish(", "producer.send(",
        "celery.send_task(", "apply_async(", "delay(",
    )
    
    QUEUE_CONSUME_PATTERNS = (
        "consume(", "receive(", "dequeue(", "listen(",
        ".consume(", ".receive(", ".dequeue(",
        "channel.basic_consume(", "consumer.receive(",
    )
    
    FILE_IO_PATTERNS = (
        "open(", "with open(", "read(", "write(",
        "file(", "pathlib", "shutil.",
        ".read(", ".write(", ".readlines(",
    )
    
    EXTERNAL_API_PATTERNS = (
        "boto3.", "google.cloud.", "azure.", "aws.",
        "kubernetes.", "slack_sdk.", "stripe.",
        "twilio.", "sendgrid.", "mailgun.",
    )
    
    def analyze(self, context: AnalysisContext) -> AnalyzerOutput:
        """Extract side effects from the analysis context.
        
        Args:
            context: AnalysisContext containing enriched_files with hunks.
            
        Returns:
            AnalyzerOutput with side_effects populated.
        """
        output = AnalyzerOutput()
        
        # Extract from enriched_files hunks
        for file_data in context.enriched_files:
            file_path = file_data.get("file_path", "")
            hunks = file_data.get("hunks", [])
            
            # Get all added lines from hunks
            added_lines = self._extract_added_lines(hunks)
            
            # Detect side effects from added lines
            for line in added_lines:
                line_lower = line.lower()
                
                # Check for database writes
                if self._matches_any(line_lower, self.DATABASE_WRITE_PATTERNS):
                    output.side_effects.append({
                        "description": f"Database write operation detected: {line[:100]}",
                        "symbol": file_path,
                        "effect_type": "database_write",
                        "confidence": 0.8,
                        "metadata": {"line": line[:200]},
                    })
                
                # Check for database reads
                if self._matches_any(line_lower, self.DATABASE_READ_PATTERNS):
                    output.side_effects.append({
                        "description": f"Database read operation detected: {line[:100]}",
                        "symbol": file_path,
                        "effect_type": "database_read",
                        "confidence": 0.8,
                        "metadata": {"line": line[:200]},
                    })
                
                # Check for cache operations
                if self._matches_any(line_lower, self.CACHE_PATTERNS):
                    output.side_effects.append({
                        "description": f"Cache operation detected: {line[:100]}",
                        "symbol": file_path,
                        "effect_type": "cache_operation",
                        "confidence": 0.8,
                        "metadata": {"line": line[:200]},
                    })
                
                # Check for HTTP calls
                if self._matches_any(line_lower, self.HTTP_CALL_PATTERNS):
                    output.side_effects.append({
                        "description": f"HTTP call detected: {line[:100]}",
                        "symbol": file_path,
                        "effect_type": "http_call",
                        "confidence": 0.8,
                        "metadata": {"line": line[:200]},
                    })
                
                # Check for queue publishing
                if self._matches_any(line_lower, self.QUEUE_PUBLISH_PATTERNS):
                    output.side_effects.append({
                        "description": f"Queue publish operation detected: {line[:100]}",
                        "symbol": file_path,
                        "effect_type": "queue_publish",
                        "confidence": 0.8,
                        "metadata": {"line": line[:200]},
                    })
                
                # Check for queue consumption
                if self._matches_any(line_lower, self.QUEUE_CONSUME_PATTERNS):
                    output.side_effects.append({
                        "description": f"Queue consume operation detected: {line[:100]}",
                        "symbol": file_path,
                        "effect_type": "queue_consume",
                        "confidence": 0.8,
                        "metadata": {"line": line[:200]},
                    })
                
                # Check for file IO
                if self._matches_any(line_lower, self.FILE_IO_PATTERNS):
                    output.side_effects.append({
                        "description": f"File IO operation detected: {line[:100]}",
                        "symbol": file_path,
                        "effect_type": "file_io",
                        "confidence": 0.7,
                        "metadata": {"line": line[:200]},
                    })
                
                # Check for external API calls
                if self._matches_any(line_lower, self.EXTERNAL_API_PATTERNS):
                    output.side_effects.append({
                        "description": f"External API call detected: {line[:100]}",
                        "symbol": file_path,
                        "effect_type": "external_api",
                        "confidence": 0.8,
                        "metadata": {"line": line[:200]},
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
    
    def _matches_any(self, text: str, patterns: tuple[str, ...]) -> bool:
        """Check if text matches any of the patterns."""
        return any(pattern in text for pattern in patterns)
    
    def _to_dict(self, value: Any) -> dict[str, Any]:
        """Convert value to dict."""
        if isinstance(value, dict):
            return value
        if hasattr(value, "model_dump"):
            return value.model_dump()
        return {}
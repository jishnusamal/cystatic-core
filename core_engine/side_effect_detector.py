from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SideEffectResult:
    """Result of side effect detection."""
    database_write: bool = False
    external_call: bool = False
    cache_write: bool = False
    queue_publish: bool = False
    details: list[str] = field(default_factory=list)
    confidence: float = 0.8


class SideEffectDetector:
    """
    Detects side effects from code changes.
    
    Heuristics:
    - Database: save(, update(, insert(, delete(, commit(, .save(, .update(, .insert(, .delete(
    - External: requests., httpx., stripe., boto3., http.client, urllib.request
    - Queue: publish(, send(, enqueue(, .publish(, .send(, .enqueue(, produce(
    - Cache: redis., cache.set, memcache., .set(, cache.add(
    """
    
    # Patterns for each side effect type
    DATABASE_PATTERNS = (
        "save(", "update(", "insert(", "delete(", "commit(",
        ".save(", ".update(", ".insert(", ".delete(", 
        "session.commit(", "session.add(", "session.delete(",
        "db.commit(", "db.add(", "db.delete(",
        "transaction.commit(", "transaction.rollback(",
    )
    
    EXTERNAL_CALL_PATTERNS = (
        "requests.", "httpx.", "stripe.", "boto3.", 
        "http.client", "urllib.request", "urllib.parse",
        "aiohttp.", "urllib3.", "urllib2.", "urllib.",
        "slack_sdk.", "twilio.", "sendgrid.", "mailgun.",
        "google.cloud.", "azure.", "aws.", "kubernetes.",
        "pika.", "amqp.", "kafka.", "redis.pubsub",
    )
    
    QUEUE_PUBLISH_PATTERNS = (
        "publish(", "send(", "enqueue(", "produce(",
        ".publish(", ".send(", ".enqueue(", ".produce(",
        "queue.put(", "channel.basic_publish(", "producer.send(",
        "celery.send_task(", "apply_async(", "delay(",
    )
    
    CACHE_WRITE_PATTERNS = (
        "redis.", "cache.set", "memcache.", "cache.set(",
        "cache.add(", "cache.put(", "cache.replace(",
        ".set(", ".add(", ".put(", ".replace(",
        "cache_client.set(", "memcached.set(",
    )
    
    def detect(self, enriched_files: list[dict]) -> dict[str, SideEffectResult]:
        """Detect side effects for each file in enriched files."""
        results = {}
        
        for file_data in enriched_files:
            file_path = str(file_data.get("file_path", ""))
            if not file_path:
                continue
            
            result = self._detect_file(file_data)
            results[file_path] = result
        
        return results
    
    def detect_for_symbol(self, enriched_files: list[dict], symbol: str) -> SideEffectResult:
        """Detect side effects for a specific symbol (file:function)."""
        file_path, function_name = self._parse_symbol(symbol)
        
        for file_data in enriched_files:
            if str(file_data.get("file_path", "")) == file_path:
                return self._detect_file_for_function(file_data, function_name)
        
        return SideEffectResult()
    
    def _detect_file(self, file_data: dict) -> SideEffectResult:
        """Detect side effects from all changes in a file."""
        effects = set()
        details = []
        
        hunks = file_data.get("hunks", []) or []
        for hunk in hunks:
            hunk_data = self._as_dict(hunk)
            for raw_line in hunk_data.get("lines", []) or []:
                line_data = self._as_dict(raw_line)
                if line_data.get("line_type") != "added":
                    continue
                content = str(line_data.get("content", "")).lower()
                
                matched = self._check_patterns(content)
                effects.update(matched)
                
                if matched:
                    details.append(f"Line: {content[:100]}")
        
        return SideEffectResult(
            database_write="database_write" in effects,
            external_call="external_call" in effects,
            cache_write="cache_write" in effects,
            queue_publish="queue_publish" in effects,
            details=details,
            confidence=0.8 if effects else 0.5
        )
    
    def _detect_file_for_function(self, file_data: dict, function_name: str) -> SideEffectResult:
        """Detect side effects specifically for a function.
        
        Note: This is a simplified version that checks the whole file.
        A more sophisticated version would parse the AST to isolate function scope.
        """
        return self._detect_file(file_data)
    
    def _check_patterns(self, content: str) -> set[str]:
        """Check content against all pattern sets."""
        effects = set()
        
        for pattern in self.DATABASE_PATTERNS:
            if pattern in content:
                effects.add("database_write")
                break
        
        for pattern in self.EXTERNAL_CALL_PATTERNS:
            if pattern in content:
                effects.add("external_call")
                break
        
        for pattern in self.QUEUE_PUBLISH_PATTERNS:
            if pattern in content:
                effects.add("queue_publish")
                break
        
        for pattern in self.CACHE_WRITE_PATTERNS:
            if pattern in content:
                effects.add("cache_write")
                break
        
        return effects
    
    def _parse_symbol(self, symbol: str) -> tuple[str, str]:
        """Parse symbol into (file_path, function_name)."""
        parts = symbol.split(":", 1)
        if len(parts) == 2:
            return parts[0], parts[1]
        return symbol, ""
    
    def _as_dict(self, value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        if hasattr(value, "model_dump"):
            return value.model_dump()
        return {}


def detect_side_effects(enriched_files: list[dict]) -> dict[str, SideEffectResult]:
    """Convenience function for side effect detection."""
    detector = SideEffectDetector()
    return detector.detect(enriched_files)
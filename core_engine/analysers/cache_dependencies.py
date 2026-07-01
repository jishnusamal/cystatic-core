"""
Cache Dependency Analyzer

Detects cache usage patterns and dependencies.
This improves predictions around stale reads and invalidation bugs.

Produces evidence types:
- reads_cache
- writes_cache
- invalidates_cache
- shared_cache
"""
from __future__ import annotations

from typing import Any
from core_engine.analysers.base import EvidenceAnalyzer, AnalyzerOutput
from core_engine.analysers.analysis_context import AnalysisContext
from core_engine.models.enums import EvidenceType


class CacheDependencyAnalyzer(EvidenceAnalyzer):
    """Detect cache usage patterns and dependencies.
    
    This analyzer:
    - Identifies cache read/write operations
    - Detects cache invalidation patterns
    - Maps shared cache dependencies
    - Never predicts failures
    - Only extracts deterministic cache facts
    """
    
    # Cache patterns to detect
    CACHE_PATTERNS = {
        # Cache decorators
        "decorators": [
            "cache",
            "cache_page",
            "cache_control",
            "cached_property",
            "lru_cache",
            "ttl_cache",
            "redis_cache",
            "memcached",
        ],
        # Cache read patterns
        "read_patterns": [
            "cache.get(",
            "cache.get_many(",
            "redis.get(",
            "memcached.get(",
            "cache.fetch(",
            "cache.read(",
        ],
        # Cache write patterns
        "write_patterns": [
            "cache.set(",
            "cache.set_many(",
            "redis.set(",
            "memcached.set(",
            "cache.put(",
            "cache.write(",
        ],
        # Cache invalidation patterns
        "invalidation_patterns": [
            "cache.delete(",
            "cache.invalidate(",
            "cache.clear(",
            "cache.flush(",
            "redis.delete(",
            "cache.invalidation",
        ],
    }
    
    # Cache system indicators
    CACHE_SYSTEMS = {
        "redis": ["redis", "Redis", "RedisCache"],
        "memcached": ["memcached", "Memcached", "MemcacheCache"],
        "memory": ["lru_cache", "in_memory", "local_cache"],
        "django": ["cache_page", "cached_property", "django.core.cache"],
    }
    
    def analyze(self, context: AnalysisContext) -> AnalyzerOutput:
        """Extract cache dependencies from the analysis context.
        
        Args:
            context: AnalysisContext containing enriched_files and changed functions.
            
        Returns:
            AnalyzerOutput with cache dependency evidence.
        """
        output = AnalyzerOutput()
        
        # Track cache operations
        cache_operations: dict[str, dict[str, list[str]]] = {}  # cache_key -> {"reads": [...], "writes": [...], "invalidations": [...]}
        
        # Extract from enriched files
        for file_data in context.enriched_files:
            file_path = file_data.get("file_path", "")
            changed_functions = file_data.get("changed_functions", [])
            keyword_signals = file_data.get("keyword_signals", [])
            
            # Check changed functions for cache patterns
            for func in changed_functions:
                func_name = self._get_func_name(func)
                if not func_name:
                    continue
                
                func_text = self._get_func_text(func)
                
                # Detect cache operations
                cache_ops = self._detect_cache_operations(func_text, keyword_signals)
                
                for cache_key, operations in cache_ops.items():
                    if cache_key not in cache_operations:
                        cache_operations[cache_key] = {"reads": [], "writes": [], "invalidations": []}
                    
                    # Add evidence for each operation
                    for op in operations:
                        if op == "read":
                            evidence_type = "reads_cache"
                            cache_operations[cache_key]["reads"].append(func_name)
                        elif op == "write":
                            evidence_type = "writes_cache"
                            cache_operations[cache_key]["writes"].append(func_name)
                        else:  # invalidate
                            evidence_type = "invalidates_cache"
                            cache_operations[cache_key]["invalidations"].append(func_name)
                        
                        output.impact_evidence.append({
                            "source_symbol": func_name,
                            "target_symbol": cache_key,
                            "evidence_type": evidence_type,
                            "confidence": 0.8,
                            "explanation": f"Function {func_name} {op}s from cache {cache_key}",
                            "metadata": {
                                "file_path": file_path,
                                "operation": op,
                                "cache_key": cache_key,
                            },
                        })
            
            # Check keyword signals for cache hints
            for signal in keyword_signals:
                signal_text = signal.keyword if hasattr(signal, "keyword") else str(signal)
                cache_keys = self._extract_cache_keys(signal_text)
                
                for cache_key in cache_keys:
                    if cache_key not in cache_operations:
                        cache_operations[cache_key] = {"reads": [], "writes": [], "invalidations": []}
                    
                    output.impact_evidence.append({
                        "source_symbol": file_path,
                        "target_symbol": cache_key,
                        "evidence_type": "reads_cache",
                        "confidence": 0.6,
                        "explanation": f"Keyword signal suggests cache access to {cache_key}",
                        "metadata": {
                            "keyword": signal_text,
                            "file_path": file_path,
                        },
                    })
        
        # Generate shared cache evidence
        # If multiple functions access the same cache, they're connected
        for cache_key, operations in cache_operations.items():
            all_functions = (
                operations["reads"] + 
                operations["writes"] + 
                operations["invalidations"]
            )
            
            if len(all_functions) > 1:
                # Remove duplicates while preserving order
                unique_functions = list(dict.fromkeys(all_functions))
                
                for i, func1 in enumerate(unique_functions):
                    for func2 in unique_functions[i+1:]:
                        # Determine operation types
                        func1_reads = func1 in operations["reads"]
                        func2_reads = func2 in operations["reads"]
                        func1_writes = func1 in operations["writes"]
                        func2_writes = func2 in operations["writes"]
                        func1_invalidates = func1 in operations["invalidations"]
                        func2_invalidates = func2 in operations["invalidations"]
                        
                        # Build explanation
                        ops = []
                        if func1_reads:
                            ops.append("reads")
                        if func1_writes:
                            ops.append("writes")
                        if func1_invalidates:
                            ops.append("invalidates")
                        func1_ops = " and ".join(ops)
                        
                        ops = []
                        if func2_reads:
                            ops.append("reads")
                        if func2_writes:
                            ops.append("writes")
                        if func2_invalidates:
                            ops.append("invalidates")
                        func2_ops = " and ".join(ops)
                        
                        explanation = f"{func1} {func1_ops} from {cache_key}, {func2} {func2_ops} from same cache"
                        
                        output.impact_evidence.append({
                            "source_symbol": func1,
                            "target_symbol": func2,
                            "evidence_type": "shared_cache",
                            "confidence": 0.75,
                            "explanation": explanation,
                            "metadata": {
                                "cache_key": cache_key,
                                "func1_operations": {
                                    "reads": func1_reads,
                                    "writes": func1_writes,
                                    "invalidates": func1_invalidates,
                                },
                                "func2_operations": {
                                    "reads": func2_reads,
                                    "writes": func2_writes,
                                    "invalidates": func2_invalidates,
                                },
                            },
                        })
        
        return output
    
    def _detect_cache_operations(self, func_text: str, keyword_signals: list) -> dict[str, list[str]]:
        """Detect cache operations in function text.
        
        Args:
            func_text: Function source code or metadata
            keyword_signals: List of keyword signals from analysis
            
        Returns:
            Dictionary mapping cache keys to list of operations
        """
        cache_operations: dict[str, list[str]] = {}
        text_lower = func_text.lower() if func_text else ""
        
        # Detect cache keys
        cache_keys = self._extract_cache_keys(func_text)
        
        if not cache_keys:
            return cache_operations
        
        # Detect read operations
        has_read = any(pattern.lower() in text_lower for pattern in self.CACHE_PATTERNS["read_patterns"])
        
        # Detect write operations
        has_write = any(pattern.lower() in text_lower for pattern in self.CACHE_PATTERNS["write_patterns"])
        
        # Detect invalidation operations
        has_invalidation = any(pattern.lower() in text_lower for pattern in self.CACHE_PATTERNS["invalidation_patterns"])
        
        # Check keyword signals for additional hints
        for signal in keyword_signals:
            signal_text = signal.keyword if hasattr(signal, "keyword") else str(signal)
            signal_lower = signal_text.lower()
            
            if any(rp.lower() in signal_lower for rp in self.CACHE_PATTERNS["read_patterns"]):
                has_read = True
            if any(wp.lower() in signal_lower for wp in self.CACHE_PATTERNS["write_patterns"]):
                has_write = True
            if any(ip.lower() in signal_lower for ip in self.CACHE_PATTERNS["invalidation_patterns"]):
                has_invalidation = True
        
        # Assign operations to cache keys
        for cache_key in cache_keys:
            operations = []
            if has_read:
                operations.append("read")
            if has_write:
                operations.append("write")
            if has_invalidation:
                operations.append("invalidate")
            
            if operations:
                cache_operations[cache_key] = operations
        
        return cache_operations
    
    def _extract_cache_keys(self, text: str) -> list[str]:
        """Extract cache keys from text.
        
        Args:
            text: Text to analyze
            
        Returns:
            List of cache keys detected
        """
        if not text:
            return []
        
        import re
        cache_keys = []
        
        # Look for cache key patterns
        # Pattern 1: String literals in cache operations
        key_pattern = r'cache\.\w+\(["\']([^"\']+)["\']'
        matches = re.findall(key_pattern, text, re.IGNORECASE)
        cache_keys.extend(matches)
        
        # Pattern 2: Variable names that look like cache keys
        var_pattern = r'cache_key\s*=\s*["\']([^"\']+)["\']'
        matches = re.findall(var_pattern, text, re.IGNORECASE)
        cache_keys.extend(matches)
        
        # Pattern 3: Common cache key patterns
        common_patterns = [
            r'(\w+_cache)',
            r'(\w+_key)',
            r'cache:\w+',
        ]
        for pattern in common_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            cache_keys.extend(matches)
        
        # Deduplicate
        cache_keys = list(set(cache_keys))
        
        return cache_keys
    
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
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional
from enum import Enum


class ChangeType(str, Enum):
    NEW_FUNCTION = "NEW_FUNCTION"
    REMOVED_FUNCTION = "REMOVED_FUNCTION"
    RETURN_VALUE_CHANGED = "RETURN_VALUE_CHANGED"
    VALIDATION_REMOVED = "VALIDATION_REMOVED"
    AUTH_CHECK_REMOVED = "AUTH_CHECK_REMOVED"


@dataclass
class BehaviorDelta:
    symbol: str
    change_type: ChangeType
    summary: str
    production_reachable: bool
    side_effects: list[str] = field(default_factory=list)


class BehaviorExtractor:
    """Extracts behavioral deltas from PR changes."""
    
    def __init__(self):
        self.risk_pattern_detector = None  # Will be set if needed
    
    def extract(self, enriched_files: list[dict], risk_patterns: list[Any] = None) -> list[BehaviorDelta]:
        """Extract behavior deltas from enriched files and risk patterns."""
        deltas: list[BehaviorDelta] = []
        
        # Build risk pattern lookup for quick checks
        risk_events_by_file = {}
        if risk_patterns:
            for risk in risk_patterns:
                risk_data = self._as_dict(risk)
                file_path = risk_data.get("file_path", "")
                if file_path not in risk_events_by_file:
                    risk_events_by_file[file_path] = []
                risk_events_by_file[file_path].append(risk_data)
        
        for file_data in enriched_files:
            file_path = str(file_data.get("file_path", ""))
            if not file_path:
                continue
            
            changed_functions = file_data.get("changed_functions", []) or []
            
            for fn in changed_functions:
                fn_data = self._as_dict(fn)
                name = str(fn_data.get("name", "")).strip()
                change_type = str(fn_data.get("change_type", "modified")).strip()
                
                if not name:
                    continue
                
                symbol = f"{file_path}:{name}"
                
                # NEW_FUNCTION
                if change_type == "added":
                    deltas.append(BehaviorDelta(
                        symbol=symbol,
                        change_type=ChangeType.NEW_FUNCTION,
                        summary=self._summarize_new_function(file_data, fn_data),
                        production_reachable=self._is_production_reachable(file_path, name),
                        side_effects=self._detect_side_effects(file_data, fn_data)
                    ))
                
                # REMOVED_FUNCTION
                elif change_type == "deleted":
                    deltas.append(BehaviorDelta(
                        symbol=symbol,
                        change_type=ChangeType.REMOVED_FUNCTION,
                        summary=f"Function {name} removed",
                        production_reachable=self._is_production_reachable(file_path, name),
                        side_effects=self._detect_side_effects(file_data, fn_data)
                    ))
                
                # RETURN_VALUE_CHANGED - check risk patterns
                elif change_type == "modified":
                    risk_events = risk_events_by_file.get(file_path, [])
                    for risk in risk_events:
                        if risk.get("type") == "FINANCIAL_LOGIC_CHANGE" or risk.get("type") == "RETURN_STATUS_FLIP":
                            if risk.get("function") == name:
                                deltas.append(BehaviorDelta(
                                    symbol=symbol,
                                    change_type=ChangeType.RETURN_VALUE_CHANGED,
                                    summary=f"Return behavior changed in {name}",
                                    production_reachable=self._is_production_reachable(file_path, name),
                                    side_effects=self._detect_side_effects(file_data, fn_data)
                                ))
        
        # VALIDATION_REMOVED - from risk patterns
        if risk_patterns:
            for risk in risk_patterns:
                risk_data = self._as_dict(risk)
                if risk_data.get("type") == "VALIDATION_REMOVED":
                    file_path = risk_data.get("file_path", "")
                    function = risk_data.get("function", "")
                    if file_path and function:
                        symbol = f"{file_path}:{function}"
                        deltas.append(BehaviorDelta(
                            symbol=symbol,
                            change_type=ChangeType.VALIDATION_REMOVED,
                            summary=f"Validation guard removed in {function}",
                            production_reachable=self._is_production_reachable(file_path, function),
                            side_effects=self._detect_side_effects_from_file(file_path, enriched_files)
                        ))
        
        # AUTH_CHECK_REMOVED - from risk patterns
        if risk_patterns:
            for risk in risk_patterns:
                risk_data = self._as_dict(risk)
                if risk_data.get("type") in ("AUTH_BYPASS", "PERMISSION_REMOVED"):
                    file_path = risk_data.get("file_path", "")
                    function = risk_data.get("function", "")
                    if file_path and function:
                        symbol = f"{file_path}:{function}"
                        deltas.append(BehaviorDelta(
                            symbol=symbol,
                            change_type=ChangeType.AUTH_CHECK_REMOVED,
                            summary=f"Auth check removed in {function}",
                            production_reachable=self._is_production_reachable(file_path, function),
                            side_effects=self._detect_side_effects_from_file(file_path, enriched_files)
                        ))
        
        # Deduplicate by symbol + change_type
        seen = set()
        unique_deltas = []
        for delta in deltas:
            key = (delta.symbol, delta.change_type)
            if key not in seen:
                seen.add(key)
                unique_deltas.append(delta)
        
        return unique_deltas
    
    def _as_dict(self, value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        if hasattr(value, "model_dump"):
            return value.model_dump()
        return {}
    
    def _summarize_new_function(self, file_data: dict, fn_data: dict) -> str:
        """Generate a summary for a new function."""
        name = str(fn_data.get("name", ""))
        file_path = str(file_data.get("file_path", "")).lower()
        
        if "test" in file_path or "test" in name.lower():
            return f"Test helper {name} added"
        if "webhook" in file_path or "webhook" in name.lower():
            return f"Webhook handler {name} added"
        if "mock" in file_path or "mock" in name.lower() or "fixture" in file_path:
            return f"Mock/fixture helper {name} added"
        
        return f"New function {name} added"
    
    def _is_production_reachable(self, file_path: str, function_name: str) -> bool:
        """Determine if a function is reachable from production code paths."""
        path_lower = file_path.lower()
        fn_lower = function_name.lower()
        
        # Not production reachable: test files
        test_markers = ("/tests/", "/test/", "/fixtures/", "/mocks/", "/examples/")
        if any(marker in path_lower for marker in test_markers):
            return False
        
        # Not production reachable: test functions
        test_fn_markers = ("test_", "_test", "mock_", "fixture_", "stub_")
        if any(fn_lower.startswith(marker) for marker in test_fn_markers):
            return False
        
        # Production reachable: typical production entry points
        prod_markers = (
            "/controllers/", "/routes/", "/api/", "/views/", "/handlers/",
            "/services/", "/workers/", "/jobs/", "/tasks/", "/endpoints/",
            "/middleware/", "/webhooks/", "/webhook/"
        )
        if any(marker in path_lower for marker in prod_markers):
            return True
        
        # Production reachable: main source directories
        main_dirs = ("/src/", "/app/", "/lib/", "/core/", "/domain/", "/application/")
        if any(marker in path_lower for marker in main_dirs):
            return True
        
        # Default: assume production reachable (conservative)
        return True
    
    def _detect_side_effects(self, file_data: dict, fn_data: dict) -> list[str]:
        """Detect side effects from a specific function's changes."""
        effects = []
        file_path = str(file_data.get("file_path", ""))
        
        # Check hunks for side effect patterns
        hunks = file_data.get("hunks", []) or []
        for hunk in hunks:
            hunk_data = self._as_dict(hunk)
            for raw_line in hunk_data.get("lines", []) or []:
                line_data = self._as_dict(raw_line)
                if line_data.get("line_type") != "added":
                    continue
                content = str(line_data.get("content", "")).lower()
                
                # Database writes
                if any(marker in content for marker in 
                       ("save(", "update(", "insert(", "delete(", "commit(", ".save(", ".update(", ".insert(", ".delete(")):
                    effects.append("database_write")
                
                # External calls
                if any(marker in content for marker in 
                       ("requests.", "httpx.", "stripe.", "boto3.", "http.client", "urllib.request")):
                    effects.append("external_call")
                
                # Queue publishes
                if any(marker in content for marker in 
                       ("publish(", "send(", "enqueue(", ".publish(", ".send(", ".enqueue(", "produce(")):
                    effects.append("queue_publish")
                
                # Cache writes
                if any(marker in content for marker in 
                       ("redis.", "cache.set", "memcache.", ".set(", "cache.add(")):
                    effects.append("cache_write")
        
        # Deduplicate
        return list(set(effects))
    
    def _detect_side_effects_from_file(self, file_path: str, enriched_files: list[dict]) -> list[str]:
        """Detect side effects from entire file context."""
        for file_data in enriched_files:
            if str(file_data.get("file_path", "")) == file_path:
                # Create a dummy fn_data to reuse _detect_side_effects logic
                dummy_fn = {"name": ""}
                return self._detect_side_effects(file_data, dummy_fn)
        return []


# For convenience, expose a function to use directly
def extract_behavior_deltas(enriched_files: list[dict], risk_patterns: list[Any] = None) -> list[BehaviorDelta]:
    extractor = BehaviorExtractor()
    return extractor.extract(enriched_files, risk_patterns)
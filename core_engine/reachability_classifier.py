from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class ReachabilityResult:
    """Result of reachability classification."""
    production_reachable: bool
    reason: str
    confidence: float = 0.8


class ReachabilityClassifier:
    """
    Classifies whether changed code is reachable from production entry points.
    
    Heuristics:
    - Test files, fixtures, mocks, examples → NOT production reachable
    - Controllers, routes, API, handlers, services, workers, jobs → production reachable
    - Main source directories (src/, app/, lib/, core/, domain/) → production reachable
    """
    
    # Directories that indicate test/non-production code
    NON_PRODUCTION_DIRS = (
        "/tests/", "/test/", "/fixtures/", "/mocks/", 
        "/examples/", "/example/", "/test_", "/testing/"
    )
    
    # Directories that indicate production entry points
    PRODUCTION_ENTRY_DIRS = (
        "/controllers/", "/routes/", "/api/", "/views/", "/handlers/",
        "/services/", "/workers/", "/jobs/", "/tasks/", "/endpoints/",
        "/middleware/", "/webhooks/", "/webhook/", "/consumers/", "/producers/"
    )
    
    # Main source directories (likely production)
    MAIN_SOURCE_DIRS = (
        "/src/", "/app/", "/lib/", "/core/", "/domain/", "/application/",
        "/business/", "/commands/", "/queries/", "/modules/", "/packages/"
    )
    
    # Function name patterns that indicate test utilities
    TEST_FUNCTION_PREFIXES = (
        "test_", "_test", "mock_", "fixture_", "stub_", "fake_", "dummy_"
    )
    
    def classify(self, file_path: str, function_name: str = "") -> ReachabilityResult:
        """Classify reachability for a file/function."""
        path_lower = file_path.lower()
        fn_lower = function_name.lower()
        
        # Check for explicit test directories
        for marker in self.NON_PRODUCTION_DIRS:
            if marker in path_lower:
                return ReachabilityResult(
                    production_reachable=False,
                    reason=f"File in test/non-production directory: {marker}",
                    confidence=0.95
                )
        
        # Check for test function prefixes
        for prefix in self.TEST_FUNCTION_PREFIXES:
            if fn_lower.startswith(prefix):
                return ReachabilityResult(
                    production_reachable=False,
                    reason=f"Function has test prefix: {prefix}",
                    confidence=0.9
                )
        
        # Check for production entry point directories
        for marker in self.PRODUCTION_ENTRY_DIRS:
            if marker in path_lower:
                return ReachabilityResult(
                    production_reachable=True,
                    reason=f"File in production entry point directory: {marker}",
                    confidence=0.9
                )
        
        # Check for main source directories
        for marker in self.MAIN_SOURCE_DIRS:
            if marker in path_lower:
                return ReachabilityResult(
                    production_reachable=True,
                    reason=f"File in main source directory: {marker}",
                    confidence=0.8
                )
        
        # Default: conservative assumption - production reachable
        return ReachabilityResult(
            production_reachable=True,
            reason="Default assumption: not in recognized test directory",
            confidence=0.5
        )
    
    def classify_batch(self, enriched_files: list[dict]) -> dict[str, ReachabilityResult]:
        """Classify reachability for all changed symbols in enriched files."""
        results = {}
        
        for file_data in enriched_files:
            file_path = str(file_data.get("file_path", ""))
            if not file_path:
                continue
            
            changed_functions = file_data.get("changed_functions", []) or []
            
            for fn in changed_functions:
                fn_data = self._as_dict(fn)
                name = str(fn_data.get("name", "")).strip()
                if not name:
                    continue
                
                symbol = f"{file_path}:{name}"
                results[symbol] = self.classify(file_path, name)
        
        return results
    
    def _as_dict(self, value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        if hasattr(value, "model_dump"):
            return value.model_dump()
        return {}


def classify_reachability(file_path: str, function_name: str = "") -> ReachabilityResult:
    """Convenience function for single classification."""
    classifier = ReachabilityClassifier()
    return classifier.classify(file_path, function_name)
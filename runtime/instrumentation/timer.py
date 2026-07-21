"""Lightweight performance instrumentation for the compiler pipeline.

Provides timing utilities with minimal overhead. Supports nested timers
with indentation and optional metadata.

Example:
    with timer("Repository Index"):
        ...

or:

    timer.start("AST Parse")
    ...
    timer.end("AST Parse")
"""

import time
from contextlib import contextmanager
from typing import Any, Generator, Optional

from runtime.errors import PipelineExecutionError


class Timer:
    """Thread-local performance timer with nested timing support.
    
    Tracks timing for compiler pipeline stages with minimal overhead.
    Supports context manager and manual start/end API.
    
    Attributes:
        _timings: List of completed timing records
        _active: Currently active timer name
        _start_time: Start time of active timer
        _depth: Current nesting depth for indentation
    """

    def __init__(self):
        """Initialize timer with empty state."""
        self._timings: list[dict[str, Any]] = []
        self._stack: list[tuple[str, float, dict[str, Any]]] = []
        self._depth: int = 0

    def start(self, name: str, metadata: Optional[dict[str, Any]] = None) -> None:
        """Start a timed section.
        
        Args:
            name: Stage name for logging
            metadata: Optional key-value pairs to log with timing
        """
        self._stack.append((name, time.perf_counter(), metadata or {}))

    def end(self, name: str) -> Optional[float]:
        """End a timed section and record the result.
        
        Args:
            name: Stage name (must match start() call)
            
        Returns:
            Elapsed time in seconds, or None if timing failed
        """
        if not self._stack:
            return None
        
        active_name, start_time, metadata = self._stack.pop()
        
        from runtime.instrumentation.logging import pipeline_logger
        if active_name != name:
            # Mismatch, but don't crash - just log it
            pipeline_logger.log_pipeline(f"[timer] WARNING: Timer mismatch - expected {active_name}, got {name}", to_terminal=False)
        
        elapsed = time.perf_counter() - start_time
        
        # Format elapsed time
        if elapsed < 1.0:
            elapsed_str = f"{elapsed * 1000:.2f}ms"
        else:
            elapsed_str = f"{elapsed:.2f}s"
        
        # Build log message
        indent = "  " * self._depth
        log_msg = f"[timer] {indent}{name:<50} {elapsed_str}"
        
        # Add metadata if present
        if metadata:
            meta_parts = [f"{k}={v}" for k, v in metadata.items()]
            log_msg += f" ({', '.join(meta_parts)})"
        
        pipeline_logger.log_pipeline(log_msg, to_terminal=False)
        
        # Record timing
        record = {
            "name": name,
            "elapsed": elapsed,
            "metadata": dict(metadata),
        }
        self._timings.append(record)
        pipeline_logger.record_timing(record)
        
        return elapsed

    @contextmanager
    def timed(self, name: str, metadata: Optional[dict[str, Any]] = None) -> Generator[None, None, None]:
        """Context manager for timing a block of code.
        
        Args:
            name: Stage name for logging
            metadata: Optional key-value pairs to log with timing
            
        Yields:
            None
            
        Example:
            with timer.timed("AST Parse"):
                tree = ast.parse(source)
        """
        self.start(name, metadata)
        self._depth += 1
        try:
            yield
        finally:
            self._depth -= 1
            self.end(name)

    def nest(self) -> None:
        """Increase nesting depth for indented timers."""
        self._depth += 1

    def unnest(self) -> None:
        """Decrease nesting depth."""
        if self._depth > 0:
            self._depth -= 1

    def get_timings(self) -> list[dict[str, Any]]:
        """Get all recorded timings.
        
        Returns:
            List of timing records with name, elapsed, and metadata
        """
        return list(self._timings)

    def get_summary(self) -> dict[str, float]:
        """Get total time per stage name.
        
        Returns:
            Dictionary mapping stage names to total elapsed time
        """
        totals: dict[str, float] = {}
        for timing in self._timings:
            name = timing["name"]
            totals[name] = totals.get(name, 0.0) + timing["elapsed"]
        return totals

    def get_slowest(self, n: int = 20) -> list[tuple[str, float]]:
        """Get the N slowest individual timed operations.
        
        Args:
            n: Number of slowest operations to return
            
        Returns:
            List of (name, elapsed) tuples sorted by elapsed time descending
        """
        sorted_timings = sorted(
            self._timings,
            key=lambda t: t["elapsed"],
            reverse=True
        )
        return [(t["name"], t["elapsed"]) for t in sorted_timings[:n]]

    def print_summary(self) -> None:
        """Print a formatted summary of all timings."""
        from runtime.instrumentation.logging import pipeline_logger
        pipeline_logger.log_pipeline("\n" + "=" * 70, to_terminal=False)
        pipeline_logger.log_pipeline("Compiler Timing Summary", to_terminal=False)
        pipeline_logger.log_pipeline("=" * 70, to_terminal=False)
        
        # Group by top-level stage
        totals = self.get_timings()
        
        # Print individual timings
        for timing in totals:
            elapsed = timing["elapsed"]
            if elapsed < 1.0:
                elapsed_str = f"{elapsed * 1000:.2f}ms"
            else:
                elapsed_str = f"{elapsed:.2f}s"
            
            name = timing["name"]
            pipeline_logger.log_pipeline(f"{name:<50} {elapsed_str}", to_terminal=False)
        
        # Print total
        total = sum(t["elapsed"] for t in totals)
        if total < 1.0:
            total_str = f"{total * 1000:.2f}ms"
        else:
            total_str = f"{total:.2f}s"
        
        pipeline_logger.log_pipeline("=" * 70, to_terminal=False)
        pipeline_logger.log_pipeline(f"{'TOTAL':<50} {total_str}", to_terminal=False)
        pipeline_logger.log_pipeline("=" * 70 + "\n", to_terminal=False)

    def print_progress(self) -> None:
        """Print intermediate timing progress."""
        if not self._timings:
            return
        
        from runtime.instrumentation.logging import pipeline_logger
        pipeline_logger.log_pipeline("\n" + "-" * 70, to_terminal=False)
        pipeline_logger.log_pipeline("Timing Progress", to_terminal=False)
        pipeline_logger.log_pipeline("-" * 70, to_terminal=False)
        
        # Print last few timings
        recent = self._timings[-5:] if len(self._timings) > 5 else self._timings
        for timing in recent:
            elapsed = timing["elapsed"]
            if elapsed < 1.0:
                elapsed_str = f"{elapsed * 1000:.2f}ms"
            else:
                elapsed_str = f"{elapsed:.2f}s"
            
            name = timing["name"]
            pipeline_logger.log_pipeline(f"{name:<50} {elapsed_str}", to_terminal=False)
        
        # Print running total
        total = sum(t["elapsed"] for t in self._timings)
        if total < 1.0:
            total_str = f"{total * 1000:.2f}ms"
        else:
            total_str = f"{total:.2f}s"
        
        pipeline_logger.log_pipeline(f"{'Running Total':<50} {total_str}", to_terminal=False)
        pipeline_logger.log_pipeline("-" * 70, to_terminal=False)

    def reset(self) -> None:
        """Clear all recorded timings."""
        self._timings.clear()
        self._stack.clear()
        self._depth = 0


# Global timer instance
timer = Timer()
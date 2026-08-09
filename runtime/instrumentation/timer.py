"""Backward-compatibility shim. The timer module is unchanged."""
import time
from contextlib import contextmanager
from typing import Any, Generator, Optional

from core.logging import pipeline_logger


class Timer:
    """Thread-local performance timer with nested timing support."""

    def __init__(self):
        self._timings: list[dict[str, Any]] = []
        self._stack: list[tuple[str, float, dict[str, Any]]] = []
        self._depth: int = 0

    def start(self, name: str, metadata: Optional[dict[str, Any]] = None) -> None:
        self._stack.append((name, time.perf_counter(), metadata or {}))

    def end(self, name: str) -> Optional[float]:
        if not self._stack:
            return None
        active_name, start_time, metadata = self._stack.pop()
        if active_name != name:
            pipeline_logger.log_pipeline(
                f"[timer] WARNING: Timer mismatch - expected {active_name}, got {name}",
                to_terminal=False,
            )
        elapsed = time.perf_counter() - start_time
        if elapsed < 1.0:
            elapsed_str = f"{elapsed * 1000:.2f}ms"
        else:
            elapsed_str = f"{elapsed:.2f}s"
        indent = "  " * self._depth
        log_msg = f"[timer] {indent}{name:<50} {elapsed_str}"
        if metadata:
            meta_parts = [f"{k}={v}" for k, v in metadata.items()]
            log_msg += f" ({', '.join(meta_parts)})"
        pipeline_logger.log_pipeline(log_msg, to_terminal=False)
        record = {"name": name, "elapsed": elapsed, "metadata": dict(metadata)}
        self._timings.append(record)
        pipeline_logger.record_timing(record)
        return elapsed

    @contextmanager
    def timed(self, name: str, metadata: Optional[dict[str, Any]] = None) -> Generator[None, None, None]:
        self.start(name, metadata)
        self._depth += 1
        try:
            yield
        finally:
            self._depth -= 1
            self.end(name)

    def nest(self) -> None:
        self._depth += 1

    def unnest(self) -> None:
        if self._depth > 0:
            self._depth -= 1

    def get_timings(self) -> list[dict[str, Any]]:
        return list(self._timings)

    def get_summary(self) -> dict[str, float]:
        totals: dict[str, float] = {}
        for timing in self._timings:
            totals[timing["name"]] = totals.get(timing["name"], 0.0) + timing["elapsed"]
        return totals

    def get_slowest(self, n: int = 20) -> list[tuple[str, float]]:
        sorted_timings = sorted(self._timings, key=lambda t: t["elapsed"], reverse=True)
        return [(t["name"], t["elapsed"]) for t in sorted_timings[:n]]

    def reset(self) -> None:
        self._timings.clear()
        self._stack.clear()
        self._depth = 0

    def print_summary(self) -> None:
        """Print a formatted summary of all timings."""
        pipeline_logger.log_pipeline("\n" + "=" * 70, to_terminal=False)
        pipeline_logger.log_pipeline("Compiler Timing Summary", to_terminal=False)
        pipeline_logger.log_pipeline("=" * 70, to_terminal=False)
        for timing in self._timings:
            elapsed = timing["elapsed"]
            elapsed_str = f"{elapsed * 1000:.2f}ms" if elapsed < 1.0 else f"{elapsed:.2f}s"
            pipeline_logger.log_pipeline(f"{timing['name']:<50} {elapsed_str}", to_terminal=False)
        total = sum(t["elapsed"] for t in self._timings)
        total_str = f"{total * 1000:.2f}ms" if total < 1.0 else f"{total:.2f}s"
        pipeline_logger.log_pipeline("=" * 70, to_terminal=False)
        pipeline_logger.log_pipeline(f"{'TOTAL':<50} {total_str}", to_terminal=False)
        pipeline_logger.log_pipeline("=" * 70 + "\n", to_terminal=False)

    def print_progress(self) -> None:
        """Print intermediate timing progress."""
        if not self._timings:
            return
        pipeline_logger.log_pipeline("\n" + "-" * 70, to_terminal=False)
        pipeline_logger.log_pipeline("Timing Progress", to_terminal=False)
        pipeline_logger.log_pipeline("-" * 70, to_terminal=False)
        recent = self._timings[-5:] if len(self._timings) > 5 else self._timings
        for timing in recent:
            elapsed = timing["elapsed"]
            elapsed_str = f"{elapsed * 1000:.2f}ms" if elapsed < 1.0 else f"{elapsed:.2f}s"
            pipeline_logger.log_pipeline(f"{timing['name']:<50} {elapsed_str}", to_terminal=False)
        total = sum(t["elapsed"] for t in self._timings)
        total_str = f"{total * 1000:.2f}ms" if total < 1.0 else f"{total:.2f}s"
        pipeline_logger.log_pipeline(f"{'Running Total':<50} {total_str}", to_terminal=False)
        pipeline_logger.log_pipeline("-" * 70, to_terminal=False)


timer = Timer()

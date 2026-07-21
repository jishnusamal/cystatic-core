"""Instrumentation for indexing passes and visitor methods.

Provides detailed timing, counting, and hotspot analysis for compiler passes.
"""

import time
import tracemalloc
from typing import Any, Callable, TypeVar
from dataclasses import dataclass, field
from functools import wraps

F = TypeVar('F', bound=Callable[..., Any])


@dataclass
class PassStats:
    """Statistics for a single indexing pass."""
    name: str
    total_time: float = 0.0
    call_count: int = 0
    max_time: float = 0.0
    min_time: float = float('inf')
    files_processed: int = 0
    slowest_files: list[tuple[str, float]] = field(default_factory=list)
    method_stats: dict[str, 'MethodStats'] = field(default_factory=dict)
    counters: dict[str, int] = field(default_factory=dict)
    memory_start: int = 0
    memory_peak: int = 0
    objects_emitted: int = 0


@dataclass
class MethodStats:
    """Statistics for a single visitor method."""
    name: str
    total_time: float = 0.0
    call_count: int = 0
    max_time: float = 0.0
    min_time: float = float('inf')
    internal_ops: dict[str, float] = field(default_factory=dict)
    counters: dict[str, int] = field(default_factory=dict)


class PassInstrumentation:
    """Instrumentation manager for indexing passes."""
    
    def __init__(self):
        self.pass_stats: dict[str, PassStats] = {}
        self.global_counters: dict[str, int] = {}
        self.start_time: float = 0.0
        self.tracemalloc_enabled: bool = False
    
    def start(self):
        """Start instrumentation."""
        self.start_time = time.perf_counter()
        try:
            tracemalloc.start()
            self.tracemalloc_enabled = True
        except Exception:
            pass
    
    def stop(self):
        """Stop instrumentation."""
        if self.tracemalloc_enabled:
            tracemalloc.stop()
    
    def get_pass_stats(self, pass_name: str) -> PassStats:
        """Get or create stats for a pass."""
        if pass_name not in self.pass_stats:
            self.pass_stats[pass_name] = PassStats(name=pass_name)
        return self.pass_stats[pass_name]
    
    def get_method_stats(self, pass_name: str, method_name: str) -> MethodStats:
        """Get or create stats for a method within a pass."""
        pass_stats = self.get_pass_stats(pass_name)
        if method_name not in pass_stats.method_stats:
            pass_stats.method_stats[method_name] = MethodStats(name=method_name)
        return pass_stats.method_stats[method_name]
    
    def record_pass_time(self, pass_name: str, elapsed: float, file_path: str):
        """Record timing for a pass execution on a file."""
        stats = self.get_pass_stats(pass_name)
        stats.total_time += elapsed
        stats.call_count += 1
        stats.max_time = max(stats.max_time, elapsed)
        stats.min_time = min(stats.min_time, elapsed)
        stats.files_processed += 1
        
        # Track slowest files
        stats.slowest_files.append((file_path, elapsed))
        stats.slowest_files.sort(key=lambda x: x[1], reverse=True)
        stats.slowest_files = stats.slowest_files[:20]
    
    def record_method_time(self, pass_name: str, method_name: str, elapsed: float):
        """Record timing for a method call."""
        stats = self.get_method_stats(pass_name, method_name)
        stats.total_time += elapsed
        stats.call_count += 1
        stats.max_time = max(stats.max_time, elapsed)
        stats.min_time = min(stats.min_time, elapsed)
    
    def record_internal_op(self, pass_name: str, method_name: str, op_name: str, elapsed: float):
        """Record timing for an internal operation within a method."""
        stats = self.get_method_stats(pass_name, method_name)
        stats.internal_ops[op_name] = stats.internal_ops.get(op_name, 0.0) + elapsed
    
    def increment_counter(self, pass_name: str, counter_name: str, amount: int = 1):
        """Increment a counter for a pass."""
        stats = self.get_pass_stats(pass_name)
        stats.counters[counter_name] = stats.counters.get(counter_name, 0) + amount
        
        # Also track globally
        self.global_counters[counter_name] = self.global_counters.get(counter_name, 0) + amount
    
    def increment_method_counter(self, pass_name: str, method_name: str, counter_name: str, amount: int = 1):
        """Increment a counter for a method."""
        stats = self.get_method_stats(pass_name, method_name)
        stats.counters[counter_name] = stats.counters.get(counter_name, 0) + amount
    
    def record_memory(self, pass_name: str):
        """Record memory usage for a pass."""
        if not self.tracemalloc_enabled:
            return
        
        stats = self.get_pass_stats(pass_name)
        current, peak = tracemalloc.get_traced_memory()
        stats.memory_peak = max(stats.memory_peak, peak)
    
    def record_objects_emitted(self, pass_name: str, count: int):
        """Record number of objects emitted by a pass."""
        stats = self.get_pass_stats(pass_name)
        stats.objects_emitted += count
    
    def print_pass_summary(self):
        """Print per-pass timing summary."""
        print("\n" + "=" * 80)
        print("VISITOR PASS SUMMARY")
        print("=" * 80)
        
        total_time = sum(s.total_time for s in self.pass_stats.values())
        
        for pass_name, stats in sorted(self.pass_stats.items(), key=lambda x: x[1].total_time, reverse=True):
            percentage = (stats.total_time / total_time * 100) if total_time > 0 else 0
            avg_time = (stats.total_time / stats.call_count * 1000) if stats.call_count > 0 else 0
            
            print(f"\n{pass_name}")
            print(f"  Total: {stats.total_time:.2f}s ({percentage:.1f}%)")
            print(f"  Calls: {stats.call_count}, Avg: {avg_time:.2f}ms, Max: {stats.max_time*1000:.2f}ms")
            
            if stats.slowest_files:
                print(f"  Slowest files:")
                for file_path, file_time in stats.slowest_files[:5]:
                    print(f"    {file_path:<50} {file_time:.2f}s")
            
            if stats.counters:
                print(f"  Counters:")
                for counter, value in sorted(stats.counters.items()):
                    print(f"    {counter}: {value}")
        
        print("\n" + "=" * 80)
        print(f"TOTAL VISITOR TIME: {total_time:.2f}s")
        print("=" * 80)
    
    def print_method_summary(self):
        """Print per-method timing summary."""
        print("\n" + "=" * 80)
        print("VISITOR METHOD SUMMARY")
        print("=" * 80)
        
        all_methods = []
        for pass_name, pass_stats in self.pass_stats.items():
            for method_name, method_stats in pass_stats.method_stats.items():
                all_methods.append((pass_name, method_name, method_stats))
        
        # Sort by total time
        all_methods.sort(key=lambda x: x[2].total_time, reverse=True)
        
        for pass_name, method_name, stats in all_methods[:20]:  # Top 20
            avg_time = (stats.total_time / stats.call_count * 1000) if stats.call_count > 0 else 0
            print(f"{pass_name}.{method_name:<30} {stats.total_time:>8.2f}s  "
                  f"calls={stats.call_count:>6}  avg={avg_time:>7.2f}ms  "
                  f"max={stats.max_time*1000:>7.2f}ms")
        
        print("=" * 80)
    
    def print_internal_ops(self, threshold_pct: float = 10.0):
        """Print internal operation breakdown for methods exceeding threshold."""
        print("\n" + "=" * 80)
        print(f"INTERNAL OPERATIONS (>{threshold_pct}% of method time)")
        print("=" * 80)
        
        for pass_name, pass_stats in self.pass_stats.items():
            for method_name, method_stats in pass_stats.method_stats.items():
                if method_stats.total_time == 0:
                    continue
                
                # Find operations exceeding threshold
                significant_ops = []
                for op_name, op_time in method_stats.internal_ops.items():
                    pct = (op_time / method_stats.total_time * 100)
                    if pct >= threshold_pct:
                        significant_ops.append((op_name, op_time, pct))
                
                if significant_ops:
                    print(f"\n{pass_name}.{method_name} (total: {method_stats.total_time:.2f}s)")
                    for op_name, op_time, pct in sorted(significant_ops, key=lambda x: x[1], reverse=True):
                        print(f"  {op_name:<40} {op_time:>8.2f}s  ({pct:>5.1f}%)")
        
        print("=" * 80)
    
    def print_top_operations(self, n: int = 50):
        """Print top N slowest operations across all passes and methods."""
        print("\n" + "=" * 80)
        print(f"TOP {n} SLOWEST OPERATIONS")
        print("=" * 80)
        
        operations = []
        
        # Add pass-level operations
        for pass_name, stats in self.pass_stats.items():
            operations.append((pass_name, None, stats.total_time, stats.call_count))
        
        # Add method-level operations
        for pass_name, pass_stats in self.pass_stats.items():
            for method_name, method_stats in pass_stats.method_stats.items():
                operations.append((pass_name, method_name, method_stats.total_time, method_stats.call_count))
        
        # Sort by total time
        operations.sort(key=lambda x: x[2], reverse=True)
        
        for i, (pass_name, method_name, total_time, call_count) in enumerate(operations[:n], 1):
            if method_name:
                name = f"{pass_name}.{method_name}"
            else:
                name = pass_name
            
            avg = (total_time / call_count * 1000) if call_count > 0 else 0
            print(f"{i:>3}. {name:<60} {total_time:>8.2f}s  "
                  f"calls={call_count:>6}  avg={avg:>7.2f}ms")
        
        print("=" * 80)
    
    def print_hotspot_analysis(self):
        """Print automatic hotspot analysis."""
        print("\n" + "=" * 80)
        print("HOTSPOT ANALYSIS")
        print("=" * 80)
        
        total_time = sum(s.total_time for s in self.pass_stats.values())
        if total_time == 0:
            print("No timing data available.")
            return
        
        # Find largest pass
        largest_pass = max(self.pass_stats.items(), key=lambda x: x[1].total_time)
        largest_pass_name, largest_pass_stats = largest_pass
        largest_pass_pct = (largest_pass_stats.total_time / total_time * 100)
        
        # Find largest method
        largest_method = None
        largest_method_time = 0
        for pass_name, pass_stats in self.pass_stats.items():
            for method_name, method_stats in pass_stats.method_stats.items():
                if method_stats.total_time > largest_method_time:
                    largest_method_time = method_stats.total_time
                    largest_method = (pass_name, method_name, method_stats)
        
        # Find most invoked method
        most_invoked = None
        most_invoked_count = 0
        for pass_name, pass_stats in self.pass_stats.items():
            for method_name, method_stats in pass_stats.method_stats.items():
                if method_stats.call_count > most_invoked_count:
                    most_invoked_count = method_stats.call_count
                    most_invoked = (pass_name, method_name, method_stats)
        
        print(f"\nVisitor Total: {total_time:.2f}s")
        print(f"\nLargest Pass: {largest_pass_name}")
        print(f"  Time: {largest_pass_stats.total_time:.2f}s ({largest_pass_pct:.1f}%)")
        
        if largest_method:
            pass_name, method_name, method_stats = largest_method
            print(f"\nLargest Method: {pass_name}.{method_name}")
            print(f"  Time: {method_stats.total_time:.2f}s")
            print(f"  Calls: {method_stats.call_count}")
            if method_stats.call_count > 0:
                print(f"  Average: {method_stats.total_time / method_stats.call_count * 1000:.2f}ms")
        
        if most_invoked:
            pass_name, method_name, method_stats = most_invoked
            print(f"\nMost Invoked: {pass_name}.{method_name}")
            print(f"  Calls: {method_stats.call_count}")
            if method_stats.call_count > 0:
                print(f"  Average: {method_stats.total_time / method_stats.call_count * 1000:.2f}ms")
        
        # Detect potential algorithmic issues
        print(f"\nPotential Algorithmic Hotspots:")
        
        # Check for repeated AST walks
        for pass_name, pass_stats in self.pass_stats.items():
            if 'ast.walk' in pass_stats.counters or 'ast.walk' in str(pass_stats.counters):
                print(f"  - {pass_name}: repeated AST traversal detected")
        
        # Check for high call counts with significant time
        for pass_name, pass_stats in self.pass_stats.items():
            for method_name, method_stats in pass_stats.method_stats.items():
                if method_stats.call_count > 1000 and method_stats.total_time > 1.0:
                    print(f"  - {pass_name}.{method_name}: {method_stats.call_count} calls, "
                          f"{method_stats.total_time:.2f}s total")
        
        print("\n" + "=" * 80)
    
    def print_counters(self):
        """Print global counters."""
        print("\n" + "=" * 80)
        print("COMPLEXITY COUNTERS")
        print("=" * 80)
        
        for counter, value in sorted(self.global_counters.items()):
            print(f"  {counter:<40} {value:>10}")
        
        print("=" * 80)


# Global instrumentation instance
_instrumentation = PassInstrumentation()


def get_instrumentation() -> PassInstrumentation:
    """Get the global instrumentation instance."""
    return _instrumentation


def time_pass(pass_name: str):
    """Decorator to time an entire pass execution."""
    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            inst = get_instrumentation()
            file_path = kwargs.get('file_path', args[1].path if len(args) > 1 else 'unknown')
            
            start = time.perf_counter()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                elapsed = time.perf_counter() - start
                inst.record_pass_time(pass_name, elapsed, file_path)
        
        return wrapper  # type: ignore
    return decorator


def time_method(pass_name: str, method_name: str):
    """Decorator to time a specific method within a pass."""
    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            inst = get_instrumentation()
            
            start = time.perf_counter()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                elapsed = time.perf_counter() - start
                inst.record_method_time(pass_name, method_name, elapsed)
        
        return wrapper  # type: ignore
    return decorator


def time_internal(pass_name: str, method_name: str, op_name: str):
    """Decorator to time an internal operation within a method."""
    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            inst = get_instrumentation()
            
            start = time.perf_counter()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                elapsed = time.perf_counter() - start
                inst.record_internal_op(pass_name, method_name, op_name, elapsed)
        
        return wrapper  # type: ignore
    return decorator


def count_objects(pass_name: str, count_name: str = "objects_emitted"):
    """Decorator to count objects emitted by a pass."""
    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            inst = get_instrumentation()
            result = func(*args, **kwargs)
            
            # Count result if it's a list or tuple
            if isinstance(result, (list, tuple)):
                inst.record_objects_emitted(pass_name, len(result))
                inst.increment_counter(pass_name, count_name, len(result))
            
            return result
        
        return wrapper  # type: ignore
    return decorator
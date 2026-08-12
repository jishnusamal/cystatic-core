import os
import time
import tracemalloc
import psutil
from typing import Optional
from contextvars import ContextVar
from core.config import get_settings
from core.logging import pipeline_logger

class MemoryProfiler:
    def __init__(self, analysis_id: Optional[str] = None):
        self.enabled = get_settings().MEMORY_PROFILING
        self.analysis_id = analysis_id or "unknown"
        self.base_rss = 0.0
        self.prev_rss = 0.0
        self.peak_rss = 0.0
        self.process = psutil.Process(os.getpid())
        self.tracemalloc_started = False
        
        if self.enabled:
            # Initialize RSS values
            rss_mb = self.process.memory_info().rss / (1024 * 1024)
            self.base_rss = rss_mb
            self.prev_rss = rss_mb
            self.peak_rss = rss_mb
            
            # Start tracemalloc
            try:
                tracemalloc.start()
                self.tracemalloc_started = True
            except Exception as e:
                pipeline_logger.log_pipeline(f"[MEMORY][analysis={self.analysis_id}] Failed to start tracemalloc: {e}", to_terminal=True)
            
            # Set this as the active profiler in context
            _current_profiler.set(self)

    def log_memory(self, stage: str):
        if not self.enabled:
            return
            
        rss_mb = self.process.memory_info().rss / (1024 * 1024)
        delta_mb = rss_mb - self.prev_rss
        if rss_mb > self.peak_rss:
            self.peak_rss = rss_mb
            
        self.prev_rss = rss_mb
        
        # Log process RSS info
        pipeline_logger.log_pipeline(
            f"[MEMORY][analysis={self.analysis_id}] stage: {stage}\n"
            f"  RSS={rss_mb:.1f} MB\n"
            f"  Δ={'+' if delta_mb >= 0 else ''}{delta_mb:.1f} MB\n"
            f"  Peak={self.peak_rss:.1f} MB",
            to_terminal=True
        )
        
        # Log tracemalloc current/peak if active
        if self.tracemalloc_started:
            try:
                current, peak = tracemalloc.get_traced_memory()
                current_mb = current / (1024 * 1024)
                peak_mb = peak / (1024 * 1024)
                pipeline_logger.log_pipeline(
                    f"[TRACEMALLOC][analysis={self.analysis_id}] current={current_mb:.1f} MB peak={peak_mb:.1f} MB",
                    to_terminal=True
                )
            except Exception as e:
                pass

    def log_tracemalloc_difference(self, stage: str, limit: int = 15):
        if not self.enabled or not self.tracemalloc_started:
            return
            
        try:
            snapshot = tracemalloc.take_snapshot()
            # Filter and display top allocations
            top_stats = snapshot.statistics('lineno')
            
            report = [f"[TRACEMALLOC-TOP][analysis={self.analysis_id}] Top allocations at stage: {stage}"]
            for index, stat in enumerate(top_stats[:limit], 1):
                frame = stat.traceback[0]
                # Format file path to be relative or clean
                filename = frame.filename
                # Shorten filename to avoid huge logs
                if "cystatic-core" in filename:
                    filename = filename.split("cystatic-core/")[-1]
                elif "site-packages" in filename:
                    filename = "site-packages/" + filename.split("site-packages/")[-1]
                size_mb = stat.size / (1024 * 1024)
                report.append(f"  {filename}:{frame.lineno} {size_mb:.2f} MB (count={stat.count})")
            
            pipeline_logger.log_pipeline("\n".join(report), to_terminal=True)
        except Exception as e:
            pipeline_logger.log_pipeline(f"[TRACEMALLOC-TOP][analysis={self.analysis_id}] Error taking snapshot: {e}", to_terminal=True)

    def stop(self):
        if self.tracemalloc_started:
            try:
                tracemalloc.stop()
                self.tracemalloc_started = False
            except Exception:
                pass
        # Clear active profiler in context
        _current_profiler.set(None)

_current_profiler: ContextVar[Optional[MemoryProfiler]] = ContextVar("current_profiler", default=None)

def get_current_profiler() -> Optional[MemoryProfiler]:
    return _current_profiler.get()

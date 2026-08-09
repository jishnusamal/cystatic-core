"""Core logging for the Factor platform.

Merges runtime/instrumentation/logging.py (PipelineLogger) and
core/runtime/log_manager.py (LogManager) into a single canonical module.
"""

from __future__ import annotations

import json
import os
import sys
import traceback
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, TextIO, TypeVar

T = TypeVar("T")


# ─── LogManager ──────────────────────────────────────────────────────────────


class LogManager:
    """Manages run-isolated, live-streamed log outputs and structured artifacts."""

    def __init__(self, log_dir: Path, run_id: str):
        self.log_dir = Path(log_dir)
        self.run_id = run_id
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # File handles for continuous live streaming
        self._handles: dict[str, TextIO] = {}
        self._open_handles()

    def _open_handles(self) -> None:
        """Open component log file handles in line-buffered text mode."""
        log_files = [
            "pipeline.log",
            "visitor.log",
            "semantic.log",
            "resolver.log",
            "performance.log",
        ]
        for name in log_files:
            file_path = self.log_dir / name
            self._handles[name] = open(
                file_path,
                "a",
                encoding="utf-8",
                buffering=1,
            )

    def log_pipeline(self, msg: str, to_terminal: bool = True) -> None:
        """Log pipeline orchestration message. Mirrors to stdout when requested."""
        handle = self._handles.get("pipeline.log")
        if handle and not handle.closed:
            handle.write(msg + "\n")
            handle.flush()
        if to_terminal:
            sys.stdout.write(msg + "\n")
            sys.stdout.flush()

    def log_visitor(self, msg: str, to_terminal: bool = False) -> None:
        """Log visitor pass execution message."""
        handle = self._handles.get("visitor.log")
        if handle and not handle.closed:
            handle.write(msg + "\n")
            handle.flush()
        if to_terminal:
            sys.stdout.write(msg + "\n")
            sys.stdout.flush()

    def log_semantic(self, msg: str, to_terminal: bool = False) -> None:
        """Log semantic resolution message."""
        handle = self._handles.get("semantic.log")
        if handle and not handle.closed:
            handle.write(msg + "\n")
            handle.flush()
        if to_terminal:
            sys.stdout.write(msg + "\n")
            sys.stdout.flush()

    def log_resolver(self, msg: str, to_terminal: bool = False) -> None:
        """Log import/call/type resolution message."""
        handle = self._handles.get("resolver.log")
        if handle and not handle.closed:
            handle.write(msg + "\n")
            handle.flush()
        if to_terminal:
            sys.stdout.write(msg + "\n")
            sys.stdout.flush()

    def log_performance(self, msg: str, to_terminal: bool = False) -> None:
        """Log performance instrumentation message."""
        handle = self._handles.get("performance.log")
        if handle and not handle.closed:
            handle.write(msg + "\n")
            handle.flush()
        if to_terminal:
            sys.stdout.write(msg + "\n")
            sys.stdout.flush()

    def log_structured_event(
        self,
        phase: str,
        event: str,
        to_terminal: bool = False,
        **kwargs: Any,
    ) -> None:
        """Log a structured JSON event to pipeline log."""
        event_data = {
            "time": datetime.now(timezone.utc).isoformat(),
            "run_id": self.run_id,
            "phase": phase,
            "event": event,
            **kwargs,
        }
        self.log_pipeline(json.dumps(event_data), to_terminal=to_terminal)

    def write_json(self, name: str, data: Any) -> None:
        """Write structured JSON artifact into the run directory."""
        if not name.endswith(".json"):
            name = f"{name}.json"
        file_path = self.log_dir / name
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)
            f.write("\n")

    def log_failure(
        self,
        exc: Exception,
        phase: str = "unknown",
        repository: str = "unknown",
        pr: str = "N/A",
        elapsed_time: float = 0.0,
    ) -> None:
        """Log a detailed failure report to pipeline.log on error."""
        tb_str = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        failure_msg = (
            "\n"
            "====================================================\n"
            "ERROR ANALYSIS FAILURE\n"
            "====================================================\n"
            f"Run ID:       {self.run_id}\n"
            f"Phase:        {phase}\n"
            f"Repository:   {repository}\n"
            f"PR:           {pr}\n"
            f"Elapsed Time: {elapsed_time:.2f}s\n"
            "----------------------------------------------------\n"
            "Stacktrace:\n"
            f"{tb_str}"
            "====================================================\n"
        )
        self.log_pipeline(failure_msg, to_terminal=True)

    def close(self) -> None:
        """Flush and close all open log file handles."""
        for handle in self._handles.values():
            if not handle.closed:
                try:
                    handle.flush()
                    handle.close()
                except Exception:
                    pass

    def __enter__(self) -> "LogManager":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()


# ─── PipelineLogger ──────────────────────────────────────────────────────────


class PipelineLogger:
    """Context-var-scoped logger that routes component logs to LogManager.

    Merged from runtime/instrumentation/logging.py.
    """

    def __init__(self) -> None:
        self._run_context_var: ContextVar[Optional[Any]] = ContextVar(
            "run_context", default=None
        )
        self._pipeline_logs_var: ContextVar[Optional[list[str]]] = ContextVar(
            "pipeline_logs", default=None
        )
        self._visitor_logs_var: ContextVar[Optional[list[str]]] = ContextVar(
            "visitor_logs", default=None
        )
        self._semantic_logs_var: ContextVar[Optional[list[str]]] = ContextVar(
            "semantic_logs", default=None
        )
        self._resolver_logs_var: ContextVar[Optional[list[str]]] = ContextVar(
            "resolver_logs", default=None
        )
        self._performance_logs_var: ContextVar[Optional[list[str]]] = ContextVar(
            "performance_logs", default=None
        )
        self._timings_var: ContextVar[Optional[list[dict[str, Any]]]] = ContextVar(
            "timings", default=None
        )
        self._call_resolutions_var: ContextVar[
            Optional[list[dict[str, Any]]]
        ] = ContextVar("call_resolutions", default=None)

        # Globals for fallback (e.g. if run outside a pipeline execution context)
        self._global_pipeline_logs: list[str] = []
        self._global_visitor_logs: list[str] = []
        self._global_semantic_logs: list[str] = []
        self._global_resolver_logs: list[str] = []
        self._global_performance_logs: list[str] = []
        self._global_timings: list[dict[str, Any]] = []
        self._global_call_resolutions: list[dict[str, Any]] = []

    def _get_list(
        self, var: ContextVar[Optional[list[T]]], fallback: list[T]
    ) -> list[T]:
        val = var.get()
        if val is None:
            return fallback
        return val

    @property
    def current_context(self) -> Optional[Any]:
        return self._run_context_var.get()

    def set_context(self, ctx: Optional[Any]) -> None:
        self._run_context_var.set(ctx)

    @property
    def pipeline_logs(self) -> list[str]:
        return self._get_list(self._pipeline_logs_var, self._global_pipeline_logs)

    @property
    def visitor_logs(self) -> list[str]:
        return self._get_list(self._visitor_logs_var, self._global_visitor_logs)

    @property
    def semantic_logs(self) -> list[str]:
        return self._get_list(self._semantic_logs_var, self._global_semantic_logs)

    @property
    def resolver_logs(self) -> list[str]:
        return self._get_list(self._resolver_logs_var, self._global_resolver_logs)

    @property
    def performance_logs(self) -> list[str]:
        return self._get_list(self._performance_logs_var, self._global_performance_logs)

    @property
    def timings(self) -> list[dict[str, Any]]:
        return self._get_list(self._timings_var, self._global_timings)

    @property
    def call_resolutions(self) -> list[dict[str, Any]]:
        return self._get_list(self._call_resolutions_var, self._global_call_resolutions)

    @property
    def is_profile(self) -> bool:
        return (
            os.environ.get("CYSTATIC_PROFILE", "").lower() in ("true", "1", "yes")
            or os.environ.get("PROFILE", "").lower() in ("true", "1", "yes")
            or "--profile" in sys.argv
        )

    @property
    def is_debug(self) -> bool:
        return (
            os.environ.get("CYSTATIC_DEBUG", "").lower() in ("true", "1", "yes")
            or os.environ.get("DEBUG", "").lower() in ("true", "1", "yes")
            or "--debug" in sys.argv
        )

    def start_run(self, run_context: Optional[Any] = None) -> None:
        self._run_context_var.set(run_context)
        self._pipeline_logs_var.set([])
        self._visitor_logs_var.set([])
        self._semantic_logs_var.set([])
        self._resolver_logs_var.set([])
        self._performance_logs_var.set([])
        self._timings_var.set([])
        self._call_resolutions_var.set([])

        self._global_pipeline_logs.clear()
        self._global_visitor_logs.clear()
        self._global_semantic_logs.clear()
        self._global_resolver_logs.clear()
        self._global_performance_logs.clear()
        self._global_timings.clear()
        self._global_call_resolutions.clear()

    def log_pipeline(self, msg: str, to_terminal: bool = False) -> None:
        self.pipeline_logs.append(msg)
        ctx = self.current_context
        if ctx and ctx.log_manager:
            ctx.log_manager.log_pipeline(msg, to_terminal=to_terminal or self.is_debug)
        elif to_terminal or self.is_debug:
            print(msg)

    def log_visitor(self, msg: str) -> None:
        self.visitor_logs.append(msg)
        ctx = self.current_context
        if ctx and ctx.log_manager:
            ctx.log_manager.log_visitor(msg, to_terminal=self.is_debug)
        elif self.is_debug:
            print(msg)

    def log_semantic(self, msg: str) -> None:
        self.semantic_logs.append(msg)
        ctx = self.current_context
        if ctx and ctx.log_manager:
            ctx.log_manager.log_semantic(msg, to_terminal=self.is_debug)
        elif self.is_debug:
            print(msg)

    def log_resolver(self, msg: str) -> None:
        self.resolver_logs.append(msg)
        ctx = self.current_context
        if ctx and ctx.log_manager:
            ctx.log_manager.log_resolver(msg, to_terminal=self.is_debug)
        elif self.is_debug:
            print(msg)

    def log_performance(self, msg: str) -> None:
        self.performance_logs.append(msg)
        ctx = self.current_context
        if ctx and ctx.log_manager:
            ctx.log_manager.log_performance(msg, to_terminal=self.is_debug)
        elif self.is_debug:
            print(msg)

    def record_timing(self, timing: dict[str, Any]) -> None:
        self.timings.append(timing)

    def record_call_resolution(self, call_data: dict[str, Any]) -> None:
        self.call_resolutions.append(call_data)

    def write_to_disk(self) -> Path:
        ctx = self.current_context
        if ctx and ctx.log_manager:
            log_dir = ctx.log_dir
            mgr = ctx.log_manager
        else:
            run_id = f"run-{datetime.now().strftime('%Y%m%d-%H%M%S')}-fallback"
            log_dir = Path("logs") / run_id
            log_dir.mkdir(parents=True, exist_ok=True)
            mgr = LogManager(log_dir, run_id)

        for line in self.pipeline_logs:
            mgr.log_pipeline(line, to_terminal=False)
        for line in self.visitor_logs:
            mgr.log_visitor(line, to_terminal=False)
        for line in self.semantic_logs:
            mgr.log_semantic(line, to_terminal=False)
        for line in self.resolver_logs:
            mgr.log_resolver(line, to_terminal=False)
        for line in self.performance_logs:
            mgr.log_performance(line, to_terminal=False)

        mgr.write_json("timings.json", self.timings)
        mgr.write_json("call_resolution.json", self.call_resolutions)

        print(f"\nDetailed profile written to:\n\n{log_dir}/\n")
        return log_dir


# Singleton logger instance used across the pipeline
pipeline_logger = PipelineLogger()


__all__ = ["LogManager", "PipelineLogger", "pipeline_logger"]

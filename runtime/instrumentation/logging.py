"""Logging and profiling output redirect manager.

Allows separating logs into stdout, profile mode, and run-scoped file outputs via LogManager.
"""

from __future__ import annotations

import json
import os
import sys
from contextvars import ContextVar
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, TypeVar

from core.runtime.run_context import RunContext

T = TypeVar("T")


class PipelineLogger:
    def __init__(self):
        self._run_context_var: ContextVar[Optional[RunContext]] = ContextVar("run_context", default=None)
        self._pipeline_logs_var: ContextVar[Optional[list[str]]] = ContextVar("pipeline_logs", default=None)
        self._visitor_logs_var: ContextVar[Optional[list[str]]] = ContextVar("visitor_logs", default=None)
        self._semantic_logs_var: ContextVar[Optional[list[str]]] = ContextVar("semantic_logs", default=None)
        self._resolver_logs_var: ContextVar[Optional[list[str]]] = ContextVar("resolver_logs", default=None)
        self._performance_logs_var: ContextVar[Optional[list[str]]] = ContextVar("performance_logs", default=None)
        self._timings_var: ContextVar[Optional[list[dict[str, Any]]]] = ContextVar("timings", default=None)
        self._call_resolutions_var: ContextVar[Optional[list[dict[str, Any]]]] = ContextVar("call_resolutions", default=None)

        # Globals for fallback (e.g. if run outside a pipeline execution context, like unit tests)
        self._global_pipeline_logs: list[str] = []
        self._global_visitor_logs: list[str] = []
        self._global_semantic_logs: list[str] = []
        self._global_resolver_logs: list[str] = []
        self._global_performance_logs: list[str] = []
        self._global_timings: list[dict[str, Any]] = []
        self._global_call_resolutions: list[dict[str, Any]] = []

    def _get_list(self, var: ContextVar[Optional[list[T]]], fallback: list[T]) -> list[T]:
        val = var.get()
        if val is None:
            return fallback
        return val

    @property
    def current_context(self) -> Optional[RunContext]:
        return self._run_context_var.get()

    def set_context(self, ctx: Optional[RunContext]) -> None:
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

    def start_run(self, run_context: Optional[RunContext] = None) -> None:
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
            from core.runtime.log_manager import LogManager
            mgr = LogManager(log_dir, run_id)

        # Write/Ensure text files are flushed
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

        # Write structured JSON artifacts
        mgr.write_json("timings.json", self.timings)
        mgr.write_json("call_resolution.json", self.call_resolutions)

        print(f"\nDetailed profile written to:\n\n{log_dir}/\n")
        return log_dir


pipeline_logger = PipelineLogger()

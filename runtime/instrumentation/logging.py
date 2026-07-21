"""Logging and profiling output redirect manager.

Allows separating logs into stdout, profile mode, and file outputs.
"""

import os
import sys
import json
from datetime import datetime
from contextvars import ContextVar
from typing import Any, Optional

class PipelineLogger:
    def __init__(self):
        self._pipeline_logs_var = ContextVar("pipeline_logs", default=None)
        self._visitor_logs_var = ContextVar("visitor_logs", default=None)
        self._semantic_logs_var = ContextVar("semantic_logs", default=None)
        self._timings_var = ContextVar("timings", default=None)
        self._call_resolutions_var = ContextVar("call_resolutions", default=None)
        
        # Globals for fallback (e.g. if run outside a pipeline execution context, like unit tests)
        self._global_pipeline_logs: list[str] = []
        self._global_visitor_logs: list[str] = []
        self._global_semantic_logs: list[str] = []
        self._global_timings: list[dict[str, Any]] = []
        self._global_call_resolutions: list[dict[str, Any]] = []

    def _get_list(self, var: ContextVar, fallback: list) -> list:
        val = var.get()
        if val is None:
            return fallback
        return val

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

    def start_run(self):
        self._pipeline_logs_var.set([])
        self._visitor_logs_var.set([])
        self._semantic_logs_var.set([])
        self._timings_var.set([])
        self._call_resolutions_var.set([])
        
        self._global_pipeline_logs.clear()
        self._global_visitor_logs.clear()
        self._global_semantic_logs.clear()
        self._global_timings.clear()
        self._global_call_resolutions.clear()

    def log_pipeline(self, msg: str, to_terminal: bool = False):
        self.pipeline_logs.append(msg)
        if to_terminal or self.is_debug:
            print(msg)

    def log_visitor(self, msg: str):
        self.visitor_logs.append(msg)
        if self.is_debug:
            print(msg)

    def log_semantic(self, msg: str):
        self.semantic_logs.append(msg)
        if self.is_debug:
            print(msg)

    def record_timing(self, timing: dict[str, Any]):
        self.timings.append(timing)

    def record_call_resolution(self, call_data: dict[str, Any]):
        self.call_resolutions.append(call_data)

    def write_to_disk(self):
        date_str = datetime.now().strftime("%Y-%m-%d")
        log_dir = os.path.join("logs", f"run-{date_str}")
        os.makedirs(log_dir, exist_ok=True)
        
        # Write files
        try:
            with open(os.path.join(log_dir, "pipeline.log"), "w", encoding="utf-8") as f:
                f.write("\n".join(self.pipeline_logs) + "\n")
        except Exception as e:
            print(f"[logging] Error writing pipeline.log: {e}")
            
        try:
            with open(os.path.join(log_dir, "visitor_profile.txt"), "w", encoding="utf-8") as f:
                f.write("\n".join(self.visitor_logs) + "\n")
        except Exception as e:
            print(f"[logging] Error writing visitor_profile.txt: {e}")
            
        try:
            with open(os.path.join(log_dir, "semantic_graph_stats.txt"), "w", encoding="utf-8") as f:
                f.write("\n".join(self.semantic_logs) + "\n")
        except Exception as e:
            print(f"[logging] Error writing semantic_graph_stats.txt: {e}")
            
        try:
            with open(os.path.join(log_dir, "timings.json"), "w", encoding="utf-8") as f:
                json.dump(self.timings, f, indent=2)
        except Exception as e:
            print(f"[logging] Error writing timings.json: {e}")
            
        try:
            with open(os.path.join(log_dir, "call_resolution.json"), "w", encoding="utf-8") as f:
                json.dump(self.call_resolutions, f, indent=2)
        except Exception as e:
            print(f"[logging] Error writing call_resolution.json: {e}")
            
        print(f"\nDetailed profile written to:\n\n{log_dir}/\n")

pipeline_logger = PipelineLogger()

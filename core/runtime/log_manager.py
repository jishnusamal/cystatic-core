"""Live-streaming, run-scoped log manager for Factor executions.

Routes component logs to dedicated files with immediate flushing, console mirroring,
and structured JSON artifact generation.
"""

from __future__ import annotations

import json
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TextIO


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
        json_str = json.dumps(event_data)
        self.log_pipeline(json_str, to_terminal=to_terminal)

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

    def __enter__(self) -> LogManager:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

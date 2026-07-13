"""Pipeline errors."""

from __future__ import annotations

from typing import Any


class PipelineError(Exception):
    """Base pipeline error."""
    
    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.details = details or {}


class PipelineExecutionError(PipelineError):
    """Pipeline execution failed."""
    pass
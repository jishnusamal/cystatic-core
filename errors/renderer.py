"""Renderer errors."""

from __future__ import annotations

from typing import Any


class RendererError(Exception):
    """Base renderer error."""
    
    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.details = details or {}


class RenderingError(RendererError):
    """Rendering failed."""
    pass
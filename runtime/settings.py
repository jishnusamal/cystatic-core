"""Backward-compatibility shim. Import from core.config instead."""

from core.config import CompilerSettings, get_compiler_settings

__all__ = ["CompilerSettings", "get_compiler_settings"]

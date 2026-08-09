"""Backward-compatibility shim. generate_run_id lives in core.runtime."""
from core.runtime import generate_run_id
__all__ = ["generate_run_id"]

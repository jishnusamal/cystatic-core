"""Backward-compatibility shim. New code should import from engine.review_context."""
from engine.review_context.compiler import ReviewContextCompiler
from engine.review_context.model import ReviewContext
__all__ = ["ReviewContextCompiler", "ReviewContext"]

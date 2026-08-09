"""Backward-compatibility shim. New code should import from engine.llm_context."""
from engine.llm_context.compiler import LLMContextCompiler
from engine.llm_context.model import LLMContext
__all__ = ["LLMContextCompiler", "LLMContext"]

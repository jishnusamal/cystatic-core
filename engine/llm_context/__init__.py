"""LLM Context Compiler — deterministic token-efficient representation of ReviewContext.

This package implements a compiler stage that derives an LLMContext from the
existing ReviewContext. The compiler is purely deterministic — it performs no
semantic interpretation, no AI/LLM usage, and no information loss.

The LLMContext is a lossless, token-efficient representation of the same
information contained in ReviewContext, optimized by eliminating representational
redundancy through:
    - Normalized lookup tables for repeated objects
    - String dictionaries for repeated strings
    - Positional arrays instead of repeated field names
    - Canonical IDs for all reusable entities
    - DAG representation for execution chains
"""

from .compiler import LLMContextCompiler
from .model import LLMContext

__all__ = ["LLMContextCompiler", "LLMContext"]

"""ReviewContext Compiler — the public ABI of Factor.

The ReviewContext is a deterministic, immutable transformation of compiler outputs
into a stable engineering context that an LLM can communicate without performing
additional discovery.

It is NOT a presentation layer.
It is NOT a serializer.
It is NOT another analysis pass.
"""

from .compiler import ReviewContextCompiler
from .model import (
    Change,
    ChangeContext,
    ChangeSummary,
    DeepestExecution,
    Discovery,
    EntryPointExecution,
    ExecutionContext,
    ExecutionStep,
    FileChange,
    ReachedComponents,
    Reference,
    ReviewContext,
    SymbolRef,
    SymbolReference,
)

__all__ = [
    "Change",
    "ChangeContext",
    "ChangeSummary",
    "DeepestExecution",
    "Discovery",
    "EntryPointExecution",
    "ExecutionContext",
    "ExecutionStep",
    "FileChange",
    "ReachedComponents",
    "Reference",
    "ReviewContext",
    "ReviewContextCompiler",
    "SymbolRef",
    "SymbolReference",
]

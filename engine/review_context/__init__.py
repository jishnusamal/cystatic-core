"""ReviewContext Compiler — the public ABI of Factor.

The ReviewContext is a deterministic, immutable transformation of compiler outputs
into a stable engineering context that an LLM can communicate without performing
additional discovery.

It is NOT a presentation layer.
It is NOT a serializer.
It is NOT another analysis pass.
"""
from .model import (
    ReviewContext,
    ChangeContext,
    ChangeSummary,
    FileChange,
    Change,
    SymbolRef,
    ExecutionContext,
    EntryPointExecution,
    ExecutionStep,
    SymbolReference,
    ReachedComponents,
    DeepestExecution,
    Discovery,
    Reference,
)
from .compiler import ReviewContextCompiler

__all__ = [
    "ReviewContext",
    "ChangeContext",
    "ChangeSummary",
    "FileChange",
    "Change",
    "SymbolRef",
    "ExecutionContext",
    "EntryPointExecution",
    "ExecutionStep",
    "SymbolReference",
    "ReachedComponents",
    "DeepestExecution",
    "Discovery",
    "Reference",
    "ReviewContextCompiler",
]

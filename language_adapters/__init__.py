"""Language-specific code analysis adapters."""

from language_adapters.languages.python.python_adapter import PythonAdapter
from language_adapters.languages.typescript.ts_adapter import TypeScriptAdapter
from language_adapters.interfaces.adapter import LanguageAdapter
from language_adapters.interfaces.graph import GraphBuilder
from language_adapters.ir import SemanticGraph

__all__ = [
    "LanguageAdapter",
    "GraphBuilder",
    "SemanticGraph",
    "PythonAdapter",
    "TypeScriptAdapter",
]

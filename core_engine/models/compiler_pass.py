"""Compiler pass contracts - immutable interfaces."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Type

from language_adapters.ir.semantic_graph import SemanticGraph

from core_engine.models.knowledge_model import KnowledgeModel


@dataclass(frozen=True)
class PassMetadata:
    """Immutable metadata for a compiler pass."""
    
    name: str
    version: str
    description: str
    dependencies: List[str] = field(default_factory=list)
    produces: List[str] = field(default_factory=list)
    consumes: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class PassResult:
    """Immutable result of a compiler pass execution."""
    
    pass_name: str
    success: bool
    diagnostics: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def with_diagnostic(self, message: str) -> PassResult:
        """Return a new PassResult with an additional diagnostic."""
        return PassResult(
            pass_name=self.pass_name,
            success=self.success,
            diagnostics=self.diagnostics + [message],
            metadata=self.metadata,
        )


class CompilerPass(ABC):
    """Abstract base class for all compiler passes.
    
    Each pass:
    - Consumes a KnowledgeModel
    - Produces an enriched KnowledgeModel
    - Is pure (no hidden state)
    - Is deterministic
    """
    
    metadata: PassMetadata
    
    @abstractmethod
    def execute(self, graph: SemanticGraph, model: KnowledgeModel) -> PassResult:
        """Execute the pass on the given graph and model.
        
        Args:
            graph: The semantic graph (read-only)
            model: The current knowledge model (will be enriched)
            
        Returns:
            PassResult indicating success/failure and diagnostics
        """
        pass
    
    def validate(self, graph: SemanticGraph) -> List[str]:
        """Validate that the graph contains required elements for this pass.
        
        Returns:
            List of validation errors (empty if valid)
        """
        return []
    
    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.metadata.name})"
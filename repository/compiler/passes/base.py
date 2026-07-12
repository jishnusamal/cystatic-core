"""Base classes for compiler passes."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from repository.model import Symbol, CallGraph, ReferenceGraph, EntryPoint


@dataclass
class PassContext:
    """
    Context passed between compiler passes.
    
    This is a mutable container that accumulates state as passes execute.
    """
    # Input from previous pass
    symbols: list[Symbol] = field(default_factory=list)
    reference_graph: ReferenceGraph | None = None
    call_graph: CallGraph | None = None
    entry_points: list[EntryPoint] = field(default_factory=list)
    
    # Intermediate data
    symbol_index: dict[str, Symbol] = field(default_factory=dict)
    file_index: dict[str, list[Symbol]] = field(default_factory=dict)
    
    # Metadata
    metadata: dict[str, Any] = field(default_factory=dict)


class CompilerPass(ABC):
    """
    Base class for all compiler passes.
    
    Each pass has a single responsibility and transforms the context
    for the next pass in the pipeline.
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Return the name of this pass."""
        pass
    
    @abstractmethod
    def run(self, context: PassContext) -> PassContext:
        """
        Execute the pass and return updated context.
        
        Args:
            context: The current pass context
            
        Returns:
            Updated pass context
        """
        pass
    
    def validate_input(self, context: PassContext) -> bool:
        """
        Validate that the context has required inputs for this pass.
        
        Override in subclasses to add validation logic.
        """
        return True
    
    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name})"
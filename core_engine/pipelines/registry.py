"""Pass registry - registration and lookup of compiler passes."""

from __future__ import annotations

from typing import Dict, List, Optional, Type

from core_engine.models.compiler_pass import CompilerPass, PassMetadata


class PassRegistry:
    """Registry for compiler passes.
    
    Manages pass registration, lookup, and dependency ordering.
    """
    
    def __init__(self):
        """Initialize empty registry."""
        self._passes: Dict[str, Type[CompilerPass]] = {}
        self._metadata: Dict[str, PassMetadata] = {}
    
    def register(self, pass_cls: Type[CompilerPass]) -> None:
        """Register a compiler pass.
        
        Args:
            pass_cls: The pass class to register
            
        Raises:
            ValueError: If a pass with the same name is already registered
        """
        metadata = pass_cls.metadata
        if metadata.name in self._passes:
            raise ValueError(
                f"Pass '{metadata.name}' is already registered"
            )
        
        self._passes[metadata.name] = pass_cls
        self._metadata[metadata.name] = metadata
    
    def get(self, name: str) -> Optional[Type[CompilerPass]]:
        """Get a pass by name.
        
        Args:
            name: The pass name
            
        Returns:
            The pass class, or None if not found
        """
        return self._passes.get(name)
    
    def get_metadata(self, name: str) -> Optional[PassMetadata]:
        """Get pass metadata by name.
        
        Args:
            name: The pass name
            
        Returns:
            The pass metadata, or None if not found
        """
        return self._metadata.get(name)
    
    def get_all(self) -> List[Type[CompilerPass]]:
        """Get all registered passes.
        
        Returns:
            List of all pass classes
        """
        return list(self._passes.values())
    
    def get_all_names(self) -> List[str]:
        """Get all registered pass names.
        
        Returns:
            List of all pass names
        """
        return list(self._passes.keys())
    
    def get_dependencies(self, name: str) -> List[str]:
        """Get dependencies for a pass.
        
        Args:
            name: The pass name
            
        Returns:
            List of dependency pass names
        """
        metadata = self._metadata.get(name)
        return metadata.dependencies if metadata else []
    
    def topological_sort(self) -> List[Type[CompilerPass]]:
        """Sort passes by dependency order.
        
        Returns:
            List of passes in execution order (dependencies first)
            
        Raises:
            ValueError: If there's a circular dependency
        """
        # Build adjacency list
        graph: Dict[str, List[str]] = {}
        for name in self._passes:
            graph[name] = self.get_dependencies(name)
        
        # Topological sort using Kahn's algorithm
        in_degree: Dict[str, int] = {name: 0 for name in graph}
        for node, deps in graph.items():
            for dep in deps:
                if dep in in_degree:
                    in_degree[node] += 1
        
        # Start with nodes that have no dependencies
        queue = [name for name, degree in in_degree.items() if degree == 0]
        sorted_names = []
        
        while queue:
            node = queue.pop(0)
            sorted_names.append(node)
            
            # Find nodes that depend on this node
            for name, deps in graph.items():
                if node in deps:
                    in_degree[name] -= 1
                    if in_degree[name] == 0:
                        queue.append(name)
        
        # Check for cycles
        if len(sorted_names) != len(graph):
            raise ValueError("Circular dependency detected in compiler passes")
        
        return [self._passes[name] for name in sorted_names]
    
    def clear(self) -> None:
        """Clear all registered passes."""
        self._passes.clear()
        self._metadata.clear()
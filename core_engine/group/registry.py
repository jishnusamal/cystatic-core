"""Group strategy registry."""

from __future__ import annotations

from typing import List

from core_engine.group import GroupStrategy


class GroupRegistry:
    """Registry for grouping strategies.
    
    Manages a collection of grouping strategies and provides methods to
    register and retrieve them.
    """
    
    def __init__(self):
        self._strategies: List[GroupStrategy] = []
    
    def register(self, strategy: GroupStrategy) -> None:
        """Register a grouping strategy.
        
        Args:
            strategy: The grouping strategy to register
        """
        self._strategies.append(strategy)
    
    def get_strategies(self) -> List[GroupStrategy]:
        """Get all registered strategies.
        
        Returns:
            List of all registered grouping strategies
        """
        return list(self._strategies)
    
    def clear(self) -> None:
        """Clear all registered strategies."""
        self._strategies.clear()
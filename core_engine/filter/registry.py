"""Filter rule registry."""

from __future__ import annotations

from typing import List

from core_engine.filter import FilterRule


class FilterRegistry:
    """Registry for filter rules.
    
    Manages a collection of filter rules and provides methods to
    register and retrieve them.
    """
    
    def __init__(self):
        self._rules: List[FilterRule] = []
    
    def register(self, rule: FilterRule) -> None:
        """Register a filter rule.
        
        Args:
            rule: The filter rule to register
        """
        self._rules.append(rule)
    
    def get_rules(self) -> List[FilterRule]:
        """Get all registered rules.
        
        Returns:
            List of all registered filter rules
        """
        return list(self._rules)
    
    def clear(self) -> None:
        """Clear all registered rules."""
        self._rules.clear()
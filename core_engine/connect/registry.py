"""Connection rule registry."""

from __future__ import annotations

from typing import List

from core_engine.connect import ConnectionRule


class ConnectionRegistry:
    """Registry for connection rules.
    
    Manages a collection of connection rules and provides methods to
    register and retrieve them.
    """
    
    def __init__(self):
        self._rules: List[ConnectionRule] = []
    
    def register(self, rule: ConnectionRule) -> None:
        """Register a connection rule.
        
        Args:
            rule: The connection rule to register
        """
        self._rules.append(rule)
    
    def get_rules(self) -> List[ConnectionRule]:
        """Get all registered rules.
        
        Returns:
            List of all registered connection rules
        """
        return list(self._rules)
    
    def clear(self) -> None:
        """Clear all registered rules."""
        self._rules.clear()
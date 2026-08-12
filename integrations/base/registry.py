"""Integration registry for managing platform integrations."""

from __future__ import annotations

from typing import Any

from integrations.base import (
    EventProvider,
    InstallationProvider,
    OutputProvider,
    RepositoryProvider,
)


class IntegrationRegistry:
    """Registry for managing integration providers.
    
    The pipeline shouldn't instantiate GitHub directly.
    Use this registry to get the appropriate integration.
    """
    
    def __init__(self) -> None:
        self._repository_providers: dict[str, RepositoryProvider] = {}
        self._event_providers: dict[str, EventProvider] = {}
        self._installation_providers: dict[str, InstallationProvider] = {}
        self._output_providers: dict[str, OutputProvider] = {}
    
    def register_repository_provider(self, name: str, provider: RepositoryProvider) -> None:
        """Register a repository provider.
        
        Args:
            name: Provider name (e.g., "github", "gitlab")
            provider: Repository provider instance
        """
        self._repository_providers[name] = provider
    
    def register_event_provider(self, name: str, provider: EventProvider) -> None:
        """Register an event provider.
        
        Args:
            name: Provider name
            provider: Event provider instance
        """
        self._event_providers[name] = provider
    
    def register_installation_provider(self, name: str, provider: InstallationProvider) -> None:
        """Register an installation provider.
        
        Args:
            name: Provider name
            provider: Installation provider instance
        """
        self._installation_providers[name] = provider
    
    def register_output_provider(self, name: str, provider: OutputProvider) -> None:
        """Register an output provider.
        
        Args:
            name: Provider name
            provider: Output provider instance
        """
        self._output_providers[name] = provider
    
    def get_repository_provider(self, name: str) -> RepositoryProvider:
        """Get a repository provider by name.
        
        Args:
            name: Provider name
            
        Returns:
            Repository provider instance
            
        Raises:
            KeyError: If provider not found
        """
        if name not in self._repository_providers:
            raise KeyError(f"Repository provider '{name}' not registered")
        return self._repository_providers[name]
    
    def get_event_provider(self, name: str) -> EventProvider:
        """Get an event provider by name.
        
        Args:
            name: Provider name
            
        Returns:
            Event provider instance
            
        Raises:
            KeyError: If provider not found
        """
        if name not in self._event_providers:
            raise KeyError(f"Event provider '{name}' not registered")
        return self._event_providers[name]
    
    def get_installation_provider(self, name: str) -> InstallationProvider:
        """Get an installation provider by name.
        
        Args:
            name: Provider name
            
        Returns:
            Installation provider instance
            
        Raises:
            KeyError: If provider not found
        """
        if name not in self._installation_providers:
            raise KeyError(f"Installation provider '{name}' not registered")
        return self._installation_providers[name]
    
    def get_output_provider(self, name: str) -> OutputProvider:
        """Get an output provider by name.
        
        Args:
            name: Provider name
            
        Returns:
            Output provider instance
            
        Raises:
            KeyError: If provider not found
        """
        if name not in self._output_providers:
            raise KeyError(f"Output provider '{name}' not registered")
        return self._output_providers[name]
    
    def register(
        self,
        name: str,
        repository_provider: RepositoryProvider | None = None,
        event_provider: EventProvider | None = None,
        installation_provider: InstallationProvider | None = None,
        output_provider: OutputProvider | None = None,
    ) -> None:
        """Register all providers for an integration.
        
        Args:
            name: Provider name
            repository_provider: Repository provider instance
            event_provider: Event provider instance
            installation_provider: Installation provider instance
            output_provider: Output provider instance
        """
        if repository_provider is not None:
            self.register_repository_provider(name, repository_provider)
        if event_provider is not None:
            self.register_event_provider(name, event_provider)
        if installation_provider is not None:
            self.register_installation_provider(name, installation_provider)
        if output_provider is not None:
            self.register_output_provider(name, output_provider)


# Global registry instance
_registry: IntegrationRegistry | None = None


def get_registry() -> IntegrationRegistry:
    """Get the global integration registry.
    
    Returns:
        Integration registry instance
    """
    global _registry
    if _registry is None:
        _registry = IntegrationRegistry()
    return _registry
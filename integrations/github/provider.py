"""GitHub integration provider - high-level façade."""

from __future__ import annotations

from typing import Any

from integrations.base import (
    EventProvider,
    InstallationProvider,
    OutputProvider,
    RepositoryProvider,
)
from integrations.github.auth import GitHubAppAuth
from integrations.github.client import GitHubClient
from integrations.github.comments import GitHubCommentProvider
from integrations.github.repositories import GitHubRepositoryProvider
from integrations.github.webhooks import GitHubWebhookProvider


class GitHubIntegration:
    """High-level façade for GitHub integration.

    Internally composes:
    - Auth
    - Client
    - Repository
    - Webhook
    - Comment
    """

    def __init__(
        self,
        app_id: str | None = None,
        private_key: str | None = None,
        client_secret: str | None = None,
        webhook_secret: str | None = None,
    ) -> None:
        """Initialize GitHub integration.

        Args:
            app_id: GitHub App ID
            private_key: GitHub App private key
            client_secret: GitHub App client secret
            webhook_secret: Webhook verification secret
        """
        self.auth = GitHubAppAuth(
            app_id=app_id or "",
            private_key=private_key or "",
            client_secret=client_secret,
        )

        self.client = GitHubClient()
        self.webhook_secret = webhook_secret

        # Initialize providers
        self._repository_provider = GitHubRepositoryProvider(auth=self.auth)
        self._webhook_provider = GitHubWebhookProvider(secret=webhook_secret)
        self._comment_provider = GitHubCommentProvider(auth=self.auth)
        self._installation_provider = self.auth  # type: ignore[assignment,return-value]

    def get_repository_provider(self) -> RepositoryProvider:
        """Get the repository provider."""
        return self._repository_provider

    def get_event_provider(self) -> EventProvider:
        """Get the event provider."""
        return self._webhook_provider

    def get_installation_provider(self) -> InstallationProvider:
        """Get the installation provider for this integration."""
        return self._installation_provider  # type: ignore[return-value]

    def get_output_provider(self) -> OutputProvider:
        """Get the output provider."""
        return self._comment_provider

    def register(self, registry: Any) -> None:
        """Register all providers with the integration registry.

        Args:
            registry: IntegrationRegistry instance
        """
        registry.register(
            name="github",
            repository_provider=self._repository_provider,
            event_provider=self._webhook_provider,
            installation_provider=self._installation_provider,
            output_provider=self._comment_provider,
        )

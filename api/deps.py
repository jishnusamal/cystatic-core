"""FastAPI dependency injection helpers.

Provides reusable dependencies for route handlers.

Usage:
    from api.deps import get_pipeline, get_registry

    @router.post("/analyze")
    async def analyze(pipeline: Pipeline = Depends(get_pipeline)):
        ...
"""

from __future__ import annotations

from typing import Any

from core.config import get_settings


def get_pipeline() -> Any:
    """Get the global Pipeline instance.

    Lazily initialises the Pipeline on first call via the GitHub integration
    registry. Suitable for use as a FastAPI Depends() dependency.
    """
    from engine.pipeline.pipeline import Pipeline
    from integrations.base.registry import get_registry
    from integrations.github.provider import GitHubIntegration

    settings = get_settings()
    registry = get_registry()

    github_integration = GitHubIntegration(
        app_id=settings.GITHUB_APP_CLIENT_ID,
        private_key=settings.GITHUB_PRIVATE_KEY,
        client_secret=settings.GITHUB_CLIENT_SECRET,
        webhook_secret=settings.GITHUB_APP_WEBHOOK_SECRET,
    )
    github_integration.register(registry)

    repository_provider = registry.get_repository_provider("github")
    output_provider = registry.get_output_provider("github")

    from engine.language.builtins import create_default_language_registry

    language_registry = create_default_language_registry()

    return Pipeline(
        language_registry=language_registry,
        repository_provider=repository_provider,
        output_provider=output_provider,
    )


def get_registry() -> Any:
    """Get the global integration registry.

    TODO: Move to a proper singleton / DI container.
    """
    from integrations.base.registry import get_registry as _get_registry
    from integrations.github.provider import GitHubIntegration

    settings = get_settings()
    registry = _get_registry()

    github_integration = GitHubIntegration(
        app_id=settings.GITHUB_APP_CLIENT_ID,
        private_key=settings.GITHUB_PRIVATE_KEY,
        client_secret=settings.GITHUB_CLIENT_SECRET,
        webhook_secret=settings.GITHUB_APP_WEBHOOK_SECRET,
    )
    github_integration.register(registry)

    return registry

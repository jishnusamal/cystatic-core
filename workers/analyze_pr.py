"""Dramatiq actor for PR analysis background jobs.

Ported from the _process_pr_analysis function in integrations/github/routes.py.
"""

from __future__ import annotations

import traceback

import dramatiq

from workers.queue import broker  # noqa: F401  — ensures broker is registered


@dramatiq.actor(queue_name="analysis", max_retries=2)
def analyze_pr(
    repo_full_name: str,
    pr_number: int,
    base_sha: str,
    head_sha: str,
    installation_id: str | None,
    delivery_id: str | None,
) -> None:
    """Background task to process PR analysis.

    Executes the analysis pipeline for a pull request and publishes the
    results as a comment on the PR via the GitHub integration output provider.

    Args:
        repo_full_name: Full repository name (owner/repo)
        pr_number: Pull request number
        base_sha: Base commit SHA
        head_sha: Head commit SHA
        installation_id: GitHub App installation ID for authentication
        delivery_id: GitHub webhook delivery ID for tracing
    """
    import asyncio

    asyncio.run(
        _process_pr_analysis(
            repo_full_name=repo_full_name,
            pr_number=pr_number,
            base_sha=base_sha,
            head_sha=head_sha,
            installation_id=installation_id,
            delivery_id=delivery_id,
        )
    )


async def _process_pr_analysis(
    repo_full_name: str,
    pr_number: int,
    base_sha: str,
    head_sha: str,
    installation_id: str | None,
    delivery_id: str | None,
) -> None:
    """Async implementation of PR analysis pipeline execution."""
    from integrations.base.registry import get_registry
    from integrations.github.provider import GitHubIntegration
    from engine.pipeline.pipeline import Pipeline
    from models.core import RepositoryReference, PullRequestReference
    from models.analysis import AnalysisRequest, AnalysisTrigger
    from core.config import get_settings

    settings = get_settings()

    # Build registry and pipeline
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
    pipeline = Pipeline(
        repository_provider=repository_provider,
        output_provider=output_provider,
    )

    owner, repo = repo_full_name.split("/", 1)
    request = AnalysisRequest(
        repository=RepositoryReference(
            provider="github",
            owner=owner,
            repository=repo,
            default_branch=base_sha or "main",
        ),
        pull_request=PullRequestReference(
            number=pr_number,
            base_sha=base_sha or "main",
            head_sha=head_sha or "main",
            title="",
        ),
        trigger=AnalysisTrigger.PULL_REQUEST,
    )

    try:
        context = await pipeline.run(request)

        if context.error:
            print(f"Pipeline failed for {repo_full_name}: {context.error}")
            return

        destination: dict = {
            "repo": repo_full_name,
            "pr_number": str(pr_number),
            "base_sha": base_sha,
            "head_sha": head_sha,
            "language": context.language or "unknown",
            "total_time": f"{context.total_time:.2f}" if context.total_time else "N/A",
        }

        if installation_id:
            installation_provider = registry.get_installation_provider("github")
            token = await installation_provider.authenticate(installation_id)
            destination["token"] = token

        # Generate LLM comment if ReviewContext is available
        if context.review_context is not None:
            try:
                llm_result = pipeline.generate_llm_comment(
                    context,
                    repository=repo_full_name,
                    pr_number=str(pr_number),
                    language=context.language or "unknown",
                )
                llm_comment = llm_result.get("comment")
                if llm_comment:
                    destination["llm_comment"] = llm_comment
            except Exception as exc:
                print(f"[analyze_pr] LLM comment generation failed: {exc}")

        await output_provider.publish(context.ocm, destination)
        print(f"Successfully analyzed {repo_full_name} PR#{pr_number}")

    except Exception as exc:
        print(f"Error processing PR analysis for {repo_full_name}: {exc}")
        traceback.print_exc()
        raise

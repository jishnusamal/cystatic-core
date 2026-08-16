"""GitHub comment output provider implementation."""

from __future__ import annotations

from typing import Any

from engine.operational.model import OperationalChangeModel
from integrations.base import OutputProvider
from integrations.github.renderers.github_renderer import GitHubRenderer


class GitHubCommentProvider(OutputProvider):
    """Implements OutputProvider for GitHub PR comments.

    Responsibilities:
    - create_comment()
    - update_comment()
    - delete_comment()

    No rendering.
    Only publishing.
    """

    def __init__(self, auth: Any | None = None) -> None:
        self.auth = auth
        self._renderer = GitHubRenderer()

    async def publish(
        self,
        ocm: OperationalChangeModel,
        destination: dict[str, Any],
    ) -> str | None:
        """Publish a PR comment.

        Args:
            ocm: Operational change model
            destination: Destination info (repo, pr_number, llm_comment)

        Returns:
            Comment ID or None
        """
        from github import Auth, Github

        repo = destination.get("repo")
        pr_number = destination.get("pr_number")

        if not repo or not pr_number:
            raise ValueError("Missing 'repo' or 'pr_number' in destination")

        # Use LLM comment if available, otherwise fall back to renderer
        llm_comment = destination.get("llm_comment")
        if llm_comment:
            comment = llm_comment
        else:
            # Render the comment using the traditional renderer
            render_context = {
                "repository": repo,
                "pr_number": pr_number,
                "base_sha": destination.get("base_sha", ""),
                "head_sha": destination.get("head_sha", ""),
                "language": destination.get("language", "unknown"),
                "total_time": destination.get("total_time", "N/A"),
            }
            comment = self._renderer.render(ocm, render_context)

        # Post to GitHub
        token = destination.get("token")
        if not token:
            raise ValueError("Missing 'token' in destination")

        github = Github(auth=Auth.Token(token))
        try:
            repository = github.get_repo(repo)
            pull_request = repository.get_pull(int(pr_number))
            issue_comment = pull_request.create_issue_comment(comment)
            return str(issue_comment.id)
        finally:
            github.close()

    async def update(
        self,
        ocm: OperationalChangeModel,
        destination: dict[str, Any],
        previous_id: str | None,
    ) -> str | None:
        """Update a previously published comment.

        Args:
            ocm: Operational change model
            destination: Destination info (repo, pr_number, llm_comment)
            previous_id: Previous comment ID

        Returns:
            Updated comment ID or None
        """
        from github import Auth, Github

        if not previous_id:
            return await self.publish(ocm, destination)

        repo = destination.get("repo")
        pr_number = destination.get("pr_number")

        if not repo or not pr_number:
            raise ValueError("Missing 'repo' or 'pr_number' in destination")

        # Use LLM comment if available, otherwise fall back to renderer
        llm_comment = destination.get("llm_comment")
        if llm_comment:
            comment = llm_comment
        else:
            # Render the comment using the traditional renderer
            render_context = {
                "repository": repo,
                "pr_number": pr_number,
                "base_sha": destination.get("base_sha", ""),
                "head_sha": destination.get("head_sha", ""),
                "language": destination.get("language", "unknown"),
                "total_time": destination.get("total_time", "N/A"),
            }
            comment = self._renderer.render(ocm, render_context)

        # Update on GitHub
        token = destination.get("token")
        if not token:
            raise ValueError("Missing 'token' in destination")

        github = Github(auth=Auth.Token(token))
        try:
            repository = github.get_repo(repo)
            pull_request = repository.get_pull(int(pr_number))

            # Get the existing comment
            existing_comment = pull_request.get_issue_comment(int(previous_id))

            # Update it
            existing_comment.edit(comment)
            return previous_id
        finally:
            github.close()

    async def delete(
        self,
        destination: dict[str, Any],
        content_id: str,
    ) -> None:
        """Delete a previously published comment.

        Args:
            destination: Destination info
            content_id: Comment ID to delete
        """
        from github import Auth, Github

        repo = destination.get("repo")
        pr_number = destination.get("pr_number")

        if not repo or not pr_number:
            raise ValueError("Missing 'repo' or 'pr_number' in destination")

        token = destination.get("token")
        if not token:
            raise ValueError("Missing 'token' in destination")

        github = Github(auth=Auth.Token(token))
        try:
            repository = github.get_repo(repo)
            pull_request = repository.get_pull(int(pr_number))

            # Get and delete the comment
            comment = pull_request.get_issue_comment(int(content_id))
            comment.delete()
        finally:
            github.close()

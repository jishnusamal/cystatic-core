"""GitHub webhook implementation."""

from __future__ import annotations

import hashlib
import hmac
from typing import Any

from integrations.base import EventProvider
from models.analysis import (
    AnalysisRequest,
    AnalysisTrigger,
    RepositoryReference,
    PullRequestReference,
)
from core.errors import WebhookVerificationError


class GitHubWebhookProvider(EventProvider):
    """Implements EventProvider for GitHub webhooks.

    Responsibilities:
    - verify_signature()
    - parse_pull_request()
    - parse_push()
    - parse_installation()

    Returns runtime events.
    Never GitHub payloads.
    """

    def __init__(self, secret: str | None = None) -> None:
        self.secret = secret

    async def verify(
        self, payload: bytes, signature: str | None, secret: str | None
    ) -> bool:
        """Verify the webhook signature.

        Args:
            payload: Raw event payload
            signature: Event signature
            secret: Verification secret

        Returns:
            True if signature is valid
        """
        if not self.secret and not secret:
            return True

        secret_to_use = secret or self.secret
        if not secret_to_use:
            return True

        if not signature or not signature.startswith("sha256="):
            return False

        expected_signature = (
            "sha256="
            + hmac.new(
                secret_to_use.encode("utf-8"),
                payload,
                hashlib.sha256,
            ).hexdigest()
        )

        return hmac.compare_digest(expected_signature, signature)

    async def parse(self, payload: dict[str, Any]) -> AnalysisRequest:
        """Parse the webhook payload into an AnalysisRequest.

        Args:
            payload: Event payload

        Returns:
            AnalysisRequest object

        Raises:
            ValueError: If payload is invalid
        """
        # Determine event type
        event_type = self._detect_event_type(payload)

        if event_type == "pull_request":
            return await self._parse_pull_request(payload)
        elif event_type == "push":
            return await self._parse_push(payload)
        elif event_type == "installation":
            return await self._parse_installation(payload)
        else:
            raise ValueError(f"Unsupported event type: {event_type}")

    def _detect_event_type(self, payload: dict[str, Any]) -> str:
        """Detect the event type from the payload.

        Args:
            payload: Event payload

        Returns:
            Event type string
        """
        if "pull_request" in payload:
            return "pull_request"
        elif "ref" in payload and "commits" in payload:
            return "push"
        elif "installation" in payload:
            return "installation"
        else:
            return "unknown"

    async def _parse_pull_request(self, payload: dict[str, Any]) -> AnalysisRequest:
        """Parse a pull request event.

        Args:
            payload: Event payload

        Returns:
            AnalysisRequest object
        """
        repository = payload.get("repository") or {}
        pull_request = payload.get("pull_request") or {}
        action = payload.get("action", "")

        # Extract repository info
        repo_full_name = repository.get("full_name")
        if not repo_full_name:
            raise ValueError("Missing repository full_name")

        parts = repo_full_name.split("/", 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid repository full name: {repo_full_name}")

        repo_ref = RepositoryReference(
            provider="github",
            owner=parts[0],
            repository=parts[1],
            default_branch=repository.get("default_branch", "main"),
        )

        # Extract PR info
        pr_number = pull_request.get("number")
        base_sha = pull_request.get("base", {}).get("sha")
        head_sha = pull_request.get("head", {}).get("sha")
        title = pull_request.get("title", "")

        if pr_number is None or base_sha is None or head_sha is None:
            raise ValueError("Missing required pull request fields")

        pr_ref = PullRequestReference(
            number=int(pr_number),
            base_sha=base_sha,
            head_sha=head_sha,
            title=title,
        )

        return AnalysisRequest(
            repository=repo_ref,
            pull_request=pr_ref,
            trigger=AnalysisTrigger.PULL_REQUEST,
            metadata={
                "action": action,
                "installation_id": payload.get("installation", {}).get("id"),
            },
        )

    async def _parse_push(self, payload: dict[str, Any]) -> AnalysisRequest:
        """Parse a push event.

        Args:
            payload: Event payload

        Returns:
            AnalysisRequest object
        """
        repository = payload.get("repository") or {}

        # Extract repository info
        repo_full_name = repository.get("full_name")
        if not repo_full_name:
            raise ValueError("Missing repository full_name")

        parts = repo_full_name.split("/", 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid repository full name: {repo_full_name}")

        repo_ref = RepositoryReference(
            provider="github",
            owner=parts[0],
            repository=parts[1],
            default_branch=repository.get("default_branch", "main"),
        )

        # Extract ref and commits
        ref = payload.get("ref", "")
        after = payload.get("after", "")
        before = payload.get("before", "")

        return AnalysisRequest(
            repository=repo_ref,
            trigger=AnalysisTrigger.PUSH,
            metadata={"ref": ref, "before": before, "after": after},
        )

    async def _parse_installation(self, payload: dict[str, Any]) -> AnalysisRequest:
        """Parse an installation event.

        Args:
            payload: Event payload

        Returns:
            AnalysisRequest object
        """
        repository = (
            payload.get("repositories", [{}])[0] if payload.get("repositories") else {}
        )

        # Extract repository info
        repo_full_name = repository.get("full_name")
        if not repo_full_name:
            raise ValueError("Missing repository full_name")

        parts = repo_full_name.split("/", 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid repository full name: {repo_full_name}")

        repo_ref = RepositoryReference(
            provider="github",
            owner=parts[0],
            repository=parts[1],
            default_branch=repository.get("default_branch", "main"),
        )

        return AnalysisRequest(
            repository=repo_ref,
            trigger=AnalysisTrigger.SCHEDULED,
            metadata={
                "action": payload.get("action"),
                "installation_id": payload.get("installation", {}).get("id"),
            },
        )

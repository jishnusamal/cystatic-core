"""GitHub source adapter package."""

from source_adapters.github.auth import GitHubAppCredentials, get_installation_token, resolve_github_token
from source_adapters.github.bot import (
    GitHubAdapter,
    GitHubBot,
    GitHubFetchResult,
    GitHubFileSnapshot,
    GitHubPublisher,
    GitHubSource,
    GitHubWebhookBot,
)
from source_adapters.github.comment_formatter import render_pull_request_comment
from source_adapters.github.event_handler import (
    PullRequestAnalysisJob,
    build_pull_request_analysis_job,
    schedule_pull_request_analysis,
    should_process_pull_request_event,
)
from source_adapters.github.github_client import build_github_clients
from source_adapters.github.webhook import verify_github_webhook_signature

__all__ = [
    "GitHubAdapter",
    "GitHubAppCredentials",
    "GitHubBot",
    "GitHubFetchResult",
    "GitHubFileSnapshot",
    "GitHubPublisher",
    "GitHubSource",
    "GitHubWebhookBot",
    "PullRequestAnalysisJob",
    "build_github_clients",
    "build_pull_request_analysis_job",
    "get_installation_token",
    "render_pull_request_comment",
    "resolve_github_token",
    "schedule_pull_request_analysis",
    "should_process_pull_request_event",
    "verify_github_webhook_signature",
]

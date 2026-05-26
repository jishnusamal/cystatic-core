"""Parse GitHub events into queueable PR jobs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import BackgroundTasks


PR_EVENT_ACTIONS = {"opened", "synchronize", "reopened"}


@dataclass(frozen=True)
class PullRequestAnalysisJob:
    installation_id: int | None
    owner: str
    repo: str
    pr_number: int
    action: str
    delivery_id: str | None = None
    head_sha: str | None = None
    base_sha: str | None = None
    title: str | None = None
    author_login: str | None = None
    merge_sha: str | None = None
    state: str | None = None
    merged: bool = False
    changed_files_count: int | None = None
    repository_id: int | None = None
    github_pr_id: int | None = None
    default_branch: str | None = None

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.repo}"


def should_process_pull_request_event(event_name: str | None, action: str | None) -> bool:
    return event_name == "pull_request" and action in PR_EVENT_ACTIONS


def build_pull_request_analysis_job(
    payload: dict[str, Any],
    delivery_id: str | None = None,
) -> PullRequestAnalysisJob:
    repository = payload.get("repository") or {}
    pull_request = payload.get("pull_request") or {}
    installation = payload.get("installation") or {}

    owner = (repository.get("owner") or {}).get("login") or ""
    repo = repository.get("name") or ""
    full_name = repository.get("full_name") or ""

    if (not owner or not repo) and "/" in full_name:
        owner, repo = full_name.split("/", 1)

    pr_number = pull_request.get("number")
    action = payload.get("action")
    head = pull_request.get("head") or {}
    base = pull_request.get("base") or {}
    installation_id = installation.get("id")

    if not owner or not repo or pr_number is None or not action:
        raise ValueError("Invalid pull_request webhook payload")

    return PullRequestAnalysisJob(
        installation_id=int(installation_id) if installation_id is not None else None,
        owner=owner,
        repo=repo,
        pr_number=int(pr_number),
        action=str(action),
        delivery_id=delivery_id,
        head_sha=head.get("sha"),
        base_sha=base.get("sha"),
        title=pull_request.get("title"),
        author_login=(pull_request.get("user") or {}).get("login"),
        merge_sha=pull_request.get("merge_commit_sha"),
        state=pull_request.get("state"),
        merged=bool(pull_request.get("merged", False)),
        changed_files_count=pull_request.get("changed_files"),
        repository_id=repository.get("id"),
        github_pr_id=pull_request.get("id"),
        default_branch=repository.get("default_branch"),
    )


def schedule_pull_request_analysis(
    background_tasks: BackgroundTasks,
    job: PullRequestAnalysisJob,
) -> None:
    from workers.analyze_pr import process_pull_request_job

    background_tasks.add_task(process_pull_request_job, job)

"""GitHub source adapter implementation."""

from __future__ import annotations

import hashlib
import base64
import hmac
from dataclasses import dataclass
from typing import Any, Dict, List
from urllib.parse import quote

import requests
from github import Auth, Github, GithubException
from requests.adapters import HTTPAdapter
from unidiff import PatchSet
from urllib3.util.retry import Retry

from instrumentation import sentry
from schemas import AnalyzeRequest, DiffHunk, DiffIR, DiffLine, FileDiff


@dataclass
class GitHubFileSnapshot:
    sha: str
    file_path: str
    content: str


@dataclass
class GitHubFetchResult:
    """Repo archive fetch result."""

    content: bytes
    ref: str
    repo: str


@dataclass(frozen=True)
class GitHubWebhookContext:
    repo: str
    pr_number: int
    action: str
    delivery_id: str | None = None


class GitHubBot:
    """GitHub API helper used by the source and publisher adapters."""

    allowed_pull_request_actions = {"opened", "reopened", "synchronize", "ready_for_review"}

    def __init__(self, token: str | None = None, base_url: str | None = None) -> None:
        self.token = token or ""
        self.base_url = (base_url or "https://api.github.com").rstrip("/")
        self.client = Github(auth=Auth.Token(self.token)) if self.token else None
        self._session = requests.Session()
        retry = Retry(
            total=3,
            connect=3,
            read=3,
            backoff_factor=1,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset(["GET", "POST"]),
        )
        adapter = HTTPAdapter(max_retries=retry)
        self._session.mount("https://", adapter)
        self._session.mount("http://", adapter)

    def close(self) -> None:
        if self.client is not None:
            self.client.close()
        self._session.close()

    def get_head_sha(self, repo: str, pr_number: int) -> str:
        repository = self._get_client().get_repo(repo)
        pull_request = repository.get_pull(pr_number)
        return pull_request.head.sha

    def fetch_file_at_sha(self, repo: str, file_path: str, sha: str) -> GitHubFileSnapshot:
        encoded_path = quote(file_path, safe="/")
        url = f"{self.base_url}/repos/{repo}/contents/{encoded_path}"
        response = self._session.get(
            url,
            headers=self._headers("application/vnd.github+json"),
            params={"ref": sha},
            timeout=30,
        )
        response.raise_for_status()

        data = response.json()
        content = base64.b64decode(data["content"]).decode("utf-8")

        return GitHubFileSnapshot(sha=sha, file_path=file_path, content=content)

    def fetch_diff(self, repo: str, pr_number: int) -> DiffIR:
        url = f"{self.base_url}/repos/{repo}/pulls/{pr_number}"
        response = self._session.get(
            url,
            headers=self._headers("application/vnd.github.v3.diff"),
            timeout=30,
        )
        response.raise_for_status()
        return self._format_diff(response.text)

    def fetch_pr_files(self, repo: str, pr_number: int) -> Dict[str, str]:
        """Fetch the content of all changed files in a PR at the head SHA.
        
        Returns a dict of file_path -> content for each changed file.
        """
        repository = self._get_client().get_repo(repo)
        pull_request = repository.get_pull(pr_number)
        head_sha = pull_request.head.sha
        
        files: Dict[str, str] = {}
        for pr_file in pull_request.get_files():
            file_path = pr_file.filename
            if not file_path.endswith(".py"):
                continue
            try:
                snapshot = self.fetch_file_at_sha(repo, file_path, head_sha)
                files[file_path] = snapshot.content
            except Exception:
                # Skip files we can't fetch
                continue
        return files

    def fetch_repo_archive(self, repo: str, ref: str = "main") -> GitHubFetchResult:
        repository = self._get_client().get_repo(repo)
        archive_url = repository.get_archive_link("zipball", ref=ref)

        response = self._session.get(archive_url, timeout=60)
        response.raise_for_status()

        return GitHubFetchResult(content=response.content, ref=ref, repo=repo)

    def post_comment(self, repo: str, pr_number: int, comment: str) -> None:
        try:
            repository = self._get_client().get_repo(repo)
            pull_request = repository.get_pull(pr_number)
            pull_request.create_issue_comment(comment)
        except GithubException as exc:
            if sentry:
                sentry.capture_exception(
                    exc,
                    dependency="github",
                    operation="post_comment",
                    repo=repo,
                    pr_number=pr_number,
                    github_status=getattr(exc, "status", None),
                    github_data=getattr(exc, "data", None),
                )
            raise

    def _format_diff(self, diff: str) -> DiffIR:
        patch = PatchSet(diff)
        files: List[FileDiff] = []

        for file in patch:
            if file.is_binary_file:
                continue

            if not file.path or not file.path.endswith(".py"):
                continue

            file_added_lines: List[int] = []
            file_removed_lines: List[int] = []
            hunks: List[DiffHunk] = []

            for hunk in file:
                hunk_added_lines: List[int] = []
                hunk_removed_lines: List[int] = []
                hunk_lines: List[DiffLine] = []

                for line in hunk:
                    source_line_no = line.source_line_no or -1
                    target_line_no = line.target_line_no or -1

                    if line.is_added:
                        hunk_added_lines.append(target_line_no)
                        file_added_lines.append(target_line_no)
                        line_type = "added"
                    elif line.is_removed:
                        hunk_removed_lines.append(source_line_no)
                        file_removed_lines.append(source_line_no)
                        line_type = "removed"
                    else:
                        line_type = "context"

                    hunk_lines.append(
                        DiffLine(
                            line_type=line_type,
                            content=line.value.rstrip("\n"),
                            source_line_no=source_line_no,
                            target_line_no=target_line_no,
                        )
                    )

                hunks.append(
                    DiffHunk(
                        file_path=file.path,
                        source_start=hunk.source_start,
                        source_length=hunk.source_length,
                        target_start=hunk.target_start,
                        target_length=hunk.target_length,
                        added_lines=hunk_added_lines,
                        removed_lines=hunk_removed_lines,
                        lines=hunk_lines,
                    )
                )

            files.append(
                FileDiff(
                    file_path=file.path,
                    added_lines=file_added_lines,
                    removed_lines=file_removed_lines,
                    hunks=hunks,
                )
            )

        return DiffIR(files=files)

    # def _get_client(self) -> Github:
    #     if self.client is None:
    #         raise ValueError("GitHub token is required")
    #     return self.client
    
    def _get_client(self) -> Github:
        return self.client or Github()

    def _headers(self, accept: str) -> Dict[str, str]:
        headers = {
            "Accept": accept,
            "User-Agent": "cystatic-core",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers


class GitHubSource(GitHubBot):
    """Backwards-compatible source adapter alias."""


class GitHubPublisher(GitHubBot):
    """Backwards-compatible publisher adapter alias."""


class GitHubAdapter(GitHubBot):
    """Backwards-compatible combined adapter alias."""


class GitHubWebhookBot(GitHubBot):
    """Webhook-facing helper for GitHub pull request events."""

    def should_process_webhook_event(self, event_name: str | None, action: str | None) -> bool:
        return event_name == "pull_request" and action in self.allowed_pull_request_actions

    def verify_webhook_signature(
        self,
        payload: bytes,
        signature: str | None,
        secret: str | None,
    ) -> bool:
        if not secret:
            return True

        if not signature or not signature.startswith("sha256="):
            return False

        expected_signature = "sha256=" + hmac.new(
            secret.encode("utf-8"),
            payload,
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(expected_signature, signature)

    def extract_webhook_context(
        self,
        payload: dict[str, Any],
        delivery_id: str | None = None,
    ) -> GitHubWebhookContext:
        repository = payload.get("repository") or {}
        pull_request = payload.get("pull_request") or {}

        repo = repository.get("full_name")
        pr_number = pull_request.get("number")
        action = payload.get("action")

        if not repo or pr_number is None or not action:
            raise ValueError("Invalid pull_request webhook payload")

        return GitHubWebhookContext(
            repo=repo,
            pr_number=int(pr_number),
            action=str(action),
            delivery_id=delivery_id,
        )

    def build_analysis_request(self, payload: dict[str, Any]) -> AnalyzeRequest:
        context = self.extract_webhook_context(payload)
        return AnalyzeRequest(repo=context.repo, pr_number=context.pr_number)


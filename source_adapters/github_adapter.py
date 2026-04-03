"""GitHub source adapter (clean architecture version)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Dict, Optional
import base64
import requests
from unidiff import PatchSet
from github import Github, Auth, GithubException


# -----------------------------
# IR Layer (Diff)
# -----------------------------
@dataclass
class FileDiff:
    file_path: str
    added_lines: List[int]
    removed_lines: List[int]


@dataclass
class DiffIR:
    files: List[FileDiff]


# -----------------------------
# Fetch Layer
# -----------------------------
@dataclass
class GitHubFileSnapshot:
    sha: str
    file_path: str
    content: str


@dataclass
class GitHubFetchResult:
    """Repo archive fetch (optional utility)."""
    content: bytes
    ref: str
    repo: str


# -----------------------------
# Base GitHub Client
# -----------------------------
class GithubBase:
    def __init__(self, token: str):
        if not token:
            raise ValueError("GitHub token is required")
        self.token = token
        self.client = Github(auth=Auth.Token(token))

    def close(self):
        self.client.close()


# -----------------------------
# Source Adapter (CORE)
# -----------------------------
class GitHubSource(GithubBase):
    """
    Responsible for:
    - resolving PR metadata (SHA)
    - fetching diffs (IR)
    - fetching file snapshots at a SHA
    """

    # -----------------------------
    # Resolve PR head SHA
    # -----------------------------
    def get_head_sha(self, repo: str, pr_number: int) -> str:
        repository = self.client.get_repo(repo)
        pr = repository.get_pull(pr_number)
        return pr.head.sha

    # -----------------------------
    # Fetch file at specific SHA
    # -----------------------------
    def fetch_file_at_sha(
        self,
        repo: str,
        file_path: str,
        sha: str
    ) -> GitHubFileSnapshot:

        url = f"https://api.github.com/repos/{repo}/contents/{file_path}"

        headers = self._headers()
        resp = requests.get(url, headers=headers, params={"ref": sha})
        resp.raise_for_status()

        data = resp.json()

        content = base64.b64decode(data["content"]).decode("utf-8")

        return GitHubFileSnapshot(
            sha=sha,
            file_path=file_path,
            content=content
        )

    # -----------------------------
    # Fetch diff → IR
    # -----------------------------
    def fetch_diff(self, repo: str, pr_number: int) -> DiffIR:
        url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}"

        resp = requests.get(url, headers=self._headers())
        resp.raise_for_status()

        diff_text = resp.text
        print(self._headers())
        return self._format_diff(diff_text)

    # -----------------------------
    # Diff → IR conversion
    # -----------------------------
    def _format_diff(self, diff: str) -> DiffIR:
        patch = PatchSet(diff)

        files: List[FileDiff] = []

        for file in patch:
            if file.is_binary_file:
                continue

            added_lines: List[int] = []
            removed_lines: List[int] = []

            for hunk in file:
                line_no = hunk.target_start

                for line in hunk:

                    if line.is_added:
                        added_lines.append(line_no)

                    if line.is_removed:
                        removed_lines.append(line_no)

                    if not line.is_removed:
                        line_no += 1

            files.append(
                FileDiff(
                    file_path=file.path,
                    added_lines=added_lines,
                    removed_lines=removed_lines,
                )
            )

        return DiffIR(files=files)

    # -----------------------------
    # Repo archive (optional utility)
    # -----------------------------
    def fetch_repo_archive(
        self,
        repo: str,
        ref: str = "main"
    ) -> GitHubFetchResult:

        repository = self.client.get_repo(repo)
        archive_url = repository.get_archive_link("zipball", ref=ref)

        response = requests.get(archive_url)
        response.raise_for_status()

        return GitHubFetchResult(
            content=response.content,
            ref=ref,
            repo=repo
        )

    # -----------------------------
    # Internal helper
    # -----------------------------
    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github.v3.diff"
        }


# -----------------------------
# Output Adapter (unchanged)
# -----------------------------
class GitHubPublisher(GithubBase):
    """Posts results back to GitHub."""

    def post_comment(self, repo: str, pr_number: int, comment: str) -> None:
        try:
            repository = self.client.get_repo(repo)
            pull_request = repository.get_pull(pr_number)

            issue = pull_request.as_issue()
            issue.create_comment(comment)

        except GithubException as e:
            raise Exception(
                f"[GitHubPublisher] Failed to post comment | "
                f"Repo: {repo} | PR: {pr_number} | Error: {e.data}"
            )
"""GitHub source adapter (clean architecture version)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Dict, Optional
import base64
import requests
from unidiff import PatchSet
from github import Github, Auth, GithubException
from instrumentation import sentry
from schemas import DiffIR, FileDiff, DiffHunk, DiffLine

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
        # print(self._headers())
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
            
        # print(DiffIR(files=files))

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
# Output Adapter
# -----------------------------
class GitHubPublisher(GithubBase):
    """Posts results back to GitHub."""

    def post_comment(self, repo: str, pr_number: int, comment: str) -> None:
        try:
            repository = self.client.get_repo(repo)
            pull_request = repository.get_pull(pr_number)
            pull_request.create_issue_comment(comment)
            
        except GithubException as e:
            if sentry:
                sentry.capture_exception(
                    e,
                    dependency="github",
                    operation="post_comment",
                    repo=repo,
                    pr_number=pr_number,
                    github_status=getattr(e, "status", None),
                    github_data=getattr(e, "data", None)
                )
            raise
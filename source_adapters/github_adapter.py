"""GitHub source adapter."""

from __future__ import annotations
from dataclasses import dataclass
from github import Github, Auth, GithubException
import requests



@dataclass
class GitHubFetchResult:
    """Placeholder for fetched GitHub archive or tree contents."""
    content: bytes
    ref: str
    repo: str

class GithubBase:
    """Base class for GitHub interactions."""
    def __init__(self, token: str | None = None) -> None:
        if not token:
            raise ValueError("GitHub token is required")
        
        self.client = Github(auth=Auth.Token(token))
            
    def close(self):
        self.client.close()

class GitHubSource(GithubBase):
    """Ingests code from GitHub."""
    
    def fetch_repo_archive(
        self,
        repo: str,
        ref: str = "main"
    ) -> GitHubFetchResult:
        repository = self.client.get_repo(f"{repo}")
        
        archive_url = repository.get_archive_link("zipball", ref=ref)
        
        response = requests.get(archive_url)
        response.raise_for_status()

        return GitHubFetchResult(
            content=response.content,
            ref=ref,
            repo=f"{repo}"
        )
    

class GitHubPublisher(GithubBase):
    """Posts results back to GitHub."""
    
    def __init__(self, token: str | None = None) -> None:
        super().__init__(token=token)

    def post_comment(self, repo: str, pr_number: int, comment: str) -> None:
        """
        Posts a comment on a GitHub Pull Request.

        :param repo: "owner/repo"
        :param pr_number: PR number
        :param comment: Markdown comment
        """
        try:
            repository = self.client.get_repo(repo)
            pull_request = repository.get_pull(pr_number)

            issue = pull_request.as_issue()
            issue.create_comment(comment)

        except GithubException as e:
            raise Exception(
                f"[GitHubPublisher] Failed to post comment | Repo: {repo} | PR: {pr_number} | Error: {e.data}"
            )
    
    
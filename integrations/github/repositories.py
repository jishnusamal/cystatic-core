"""GitHub repository provider implementation."""

from __future__ import annotations

from typing import Any

from github import Auth, Github, GithubException

from integrations.base import RepositoryProvider
from integrations.github.auth import GitHubAppAuth
from integrations.github.client import GitHubClient
from runtime.models import RepositoryReference, RepositorySnapshot, DiffSnapshot, DiffFile, DiffHunk
from errors.repository import RepositoryNotFound, RepositoryAccessDenied


class GitHubRepositoryProvider(RepositoryProvider):
    """Implements RepositoryProvider for GitHub.
    
    Responsibilities:
    - fetch_repository()
    - fetch_tree()
    - fetch_diff()
    - fetch_file()
    - fetch_commit()
    """
    
    def __init__(self, auth: GitHubAppAuth | None = None) -> None:
        self.auth = auth
    
    async def fetch_repository(self, repo_ref: RepositoryReference) -> RepositorySnapshot:
        """Fetch the complete repository state.
        
        Args:
            repo_ref: Repository reference
            
        Returns:
            Repository snapshot with tree, files, and commit info
        """
        # This would typically fetch the repository archive
        # For now, raise NotImplementedError as this requires additional implementation
        raise NotImplementedError("Repository archive fetching not yet implemented")
    
    async def fetch_diff(
        self,
        repo_ref: RepositoryReference,
        base_sha: str,
        head_sha: str,
    ) -> DiffSnapshot:
        """Fetch the diff between two commits.
        
        Args:
            repo_ref: Repository reference
            base_sha: Base commit SHA
            head_sha: Head commit SHA
            
        Returns:
            Diff snapshot with changed files and hunks
        """
        # This would fetch the diff between commits
        # For now, raise NotImplementedError
        raise NotImplementedError("Diff fetching between commits not yet implemented")
    
    async def fetch_file(
        self,
        repo_ref: RepositoryReference,
        file_path: str,
        sha: str,
    ) -> str:
        """Fetch a single file at a specific commit.
        
        Args:
            repo_ref: Repository reference
            file_path: Path to the file
            sha: Commit SHA
            
        Returns:
            File content as string
        """
        from urllib.parse import quote
        import base64
        
        client = GitHubClient()
        try:
            encoded_path = quote(file_path, safe="/")
            url = f"/repos/{repo_ref.full_name}/contents/{encoded_path}"
            response = client.get(
                url,
                headers={"Accept": "application/vnd.github+json"},
                params={"ref": sha},
                timeout=30,
            )
            response.raise_for_status()
            
            data = response.json()
            content = base64.b64decode(data["content"]).decode("utf-8")
            return content
        except GithubException as exc:
            if exc.status == 404:
                raise RepositoryNotFound(f"File not found: {file_path}", details={"file": file_path, "sha": sha})
            elif exc.status == 403:
                raise RepositoryAccessDenied(f"Access denied to file: {file_path}", details={"file": file_path})
            raise
        finally:
            client.close()
    
    async def fetch_tree(
        self,
        repo_ref: RepositoryReference,
        sha: str,
    ) -> dict[str, Any]:
        """Fetch the file tree at a specific commit.
        
        Args:
            repo_ref: Repository reference
            sha: Commit SHA
            
        Returns:
            Tree structure
        """
        client = GitHubClient()
        try:
            # First get the commit to get the tree SHA
            commit = await self.fetch_commit(repo_ref, sha)
            tree_sha = commit.get("tree", {}).get("sha")
            
            if not tree_sha:
                raise ValueError(f"No tree found for commit {sha}")
            
            # Fetch the tree
            response = client.get(
                f"/repos/{repo_ref.full_name}/git/trees/{tree_sha}",
                headers={"Accept": "application/vnd.github+json"},
                params={"recursive": "1"},
                timeout=30,
            )
            response.raise_for_status()
            
            tree_data = response.json()
            return {
                "sha": tree_data.get("sha"),
                "tree": tree_data.get("tree", []),
                "truncated": tree_data.get("truncated", False),
            }
        finally:
            client.close()
    
    async def fetch_commit(
        self,
        repo_ref: RepositoryReference,
        sha: str,
    ) -> dict[str, Any]:
        """Fetch commit information.
        
        Args:
            repo_ref: Repository reference
            sha: Commit SHA
            
        Returns:
            Commit information
        """
        client = GitHubClient()
        try:
            response = client.get(
                f"/repos/{repo_ref.full_name}/commits/{sha}",
                headers={"Accept": "application/vnd.github+json"},
                timeout=30,
            )
            response.raise_for_status()
            
            commit_data = response.json()
            return {
                "sha": commit_data.get("sha"),
                "message": commit_data.get("commit", {}).get("message"),
                "author": commit_data.get("commit", {}).get("author", {}).get("name"),
                "date": commit_data.get("commit", {}).get("author", {}).get("date"),
                "tree": commit_data.get("commit", {}).get("tree"),
            }
        finally:
            client.close()
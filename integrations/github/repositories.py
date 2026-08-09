"""GitHub repository provider implementation."""

from __future__ import annotations

from typing import Any

from github import Auth, Github, GithubException

from integrations.base import RepositoryProvider
from integrations.github.auth import GitHubAppAuth
from integrations.github.client import GitHubClient
from models.core import RepositoryReference, RepositorySnapshot, DiffSnapshot, DiffFile, DiffHunk
from core.errors import RepositoryNotFound, RepositoryAccessDenied


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
    
    def _get_client(self) -> GitHubClient:
        """Create an authenticated GitHub client.
        
        Uses a PAT from settings first (preferred for repository content API calls),
        falls back to app JWT if no PAT is configured, then unauthenticated as last resort.
        
        Returns:
            GitHubClient instance (authenticated if credentials are available)
        """
        # Prefer PAT from settings (works for repository content endpoints)
        from core.config import get_settings
        settings = get_settings()
        pat = settings.GITHUB_ACCESS_TOKEN
        if pat:
            return GitHubClient(token=pat)
        
        # Fall back to app JWT (only works for app-level endpoints)
        if self.auth:
            jwt_token = self.auth.generate_jwt()
            return GitHubClient(token=jwt_token)
        return GitHubClient()
    
    async def fetch_repository(self, repo_ref: RepositoryReference) -> RepositorySnapshot:
        """Fetch the complete repository state.
        
        Downloads the repository as a zipball archive and extracts text files.
        
        Args:
            repo_ref: Repository reference
            
        Returns:
            Repository snapshot with tree, files, and commit info
        """
        return await self.fetch_repository_at_sha(repo_ref, repo_ref.default_branch)
    
    async def fetch_repository_at_sha(
        self, repo_ref: RepositoryReference, sha: str
    ) -> RepositorySnapshot:
        """Fetch the repository state at a specific commit.
        
        Downloads the repository as a zipball archive at the specified commit
        and extracts text files.
        
        Args:
            repo_ref: Repository reference
            sha: Commit SHA to fetch
            
        Returns:
            Repository snapshot at the specified commit
        """
        import zipfile
        import io

        print(f"[repositories] fetch_repository_at_sha: {repo_ref.full_name}, sha={sha}")

        # Fetch commit info
        commit = await self.fetch_commit(repo_ref, sha)
        commit_sha = commit.get("sha", "")
        print(f"[repositories] Commit SHA: {commit_sha}")

        # Download the repository as a zipball at the specific commit
        client = self._get_client()
        try:
            print(f"[repositories] Downloading zipball for {repo_ref.full_name} at {sha}...")
            response = client.get(
                f"/repos/{repo_ref.full_name}/zipball/{sha}",
                headers={"Accept": "application/vnd.github+json"},
                timeout=120,
            )
            response.raise_for_status()
            print(f"[repositories] Zipball downloaded: {len(response.content)} bytes")
        finally:
            client.close()

        # Extract files from the zip archive
        files: dict[str, str] = {}
        tree_entries: list[dict[str, Any]] = []
        
        with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
            all_names = zf.namelist()
            print(f"[repositories] Zipball entries: {len(all_names)}")
            if not all_names:
                return RepositorySnapshot(tree={}, files={}, commit=commit_sha)
            
            root_prefix = all_names[0]
            text_count = 0
            binary_count = 0
            for name in all_names:
                relative_name = name[len(root_prefix):] if name.startswith(root_prefix) else name
                
                if not relative_name:
                    continue
                
                if zf.getinfo(name).is_dir():
                    tree_entries.append({
                        "path": relative_name.rstrip("/"),
                        "type": "tree",
                        "mode": "040000",
                    })
                else:
                    tree_entries.append({
                        "path": relative_name,
                        "type": "blob",
                        "mode": "100644",
                        "sha": "",
                    })
                    
                    try:
                        raw = zf.read(name)
                        content = raw.decode("utf-8")
                        files[relative_name] = content
                        text_count += 1
                    except (UnicodeDecodeError, UnicodeError):
                        binary_count += 1
                        continue

        print(f"[repositories] Extracted: {text_count} text files, {binary_count} binary files skipped")

        tree = {
            "sha": "",
            "tree": tree_entries,
            "truncated": False,
        }

        return RepositorySnapshot(
            tree=tree,
            files=files,
            commit=commit_sha,
        )
    
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
        client = self._get_client()
        try:
            response = client.get(
                f"/repos/{repo_ref.full_name}/compare/{base_sha}...{head_sha}",
                headers={"Accept": "application/vnd.github.v3.diff"},
                timeout=30,
            )
            response.raise_for_status()
            
            diff_text = response.text
            patches = tuple(line for line in diff_text.splitlines() if line)
            
            # Parse the unified diff into DiffFile/DiffHunk structures
            files: list[DiffFile] = []
            current_file: dict[str, Any] = {}
            current_hunk: dict[str, Any] = {}
            added_lines: list[int] = []
            removed_lines: list[int] = []
            hunk_lines: list[dict[str, Any]] = []
            hunks: list[DiffHunk] = []
            
            for line in diff_text.splitlines():
                # Detect file headers: "diff --git a/path b/path"
                if line.startswith("diff --git "):
                    # Save previous file if exists
                    if current_file.get("file_path"):
                        if current_hunk:
                            hunks.append(DiffHunk(
                                file_path=current_hunk.get("file_path", ""),
                                source_start=current_hunk.get("source_start", 0),
                                source_length=current_hunk.get("source_length", 0),
                                target_start=current_hunk.get("target_start", 0),
                                target_length=current_hunk.get("target_length", 0),
                                added_lines=tuple(added_lines),
                                removed_lines=tuple(removed_lines),
                                lines=tuple(hunk_lines),
                            ))
                        files.append(DiffFile(
                            file_path=current_file["file_path"],
                            added_lines=tuple(added_lines),
                            removed_lines=tuple(removed_lines),
                            hunks=tuple(hunks),
                        ))
                    
                    # Parse new file path
                    parts = line.split()
                    file_path = parts[3][2:] if len(parts) > 3 else ""  # "b/path"
                    current_file = {"file_path": file_path}
                    current_hunk = {}
                    added_lines = []
                    removed_lines = []
                    hunk_lines = []
                    hunks = []
                
                # Detect hunk headers: "@@ -start,length +start,length @@ ..."
                elif line.startswith("@@"):
                    if current_hunk:
                        hunks.append(DiffHunk(
                            file_path=current_hunk.get("file_path", ""),
                            source_start=current_hunk.get("source_start", 0),
                            source_length=current_hunk.get("source_length", 0),
                            target_start=current_hunk.get("target_start", 0),
                            target_length=current_hunk.get("target_length", 0),
                            added_lines=tuple(added_lines),
                            removed_lines=tuple(removed_lines),
                            lines=tuple(hunk_lines),
                        ))
                    
                    import re
                    match = re.match(r"@@ -(\d+),?(\d*) \+(\d+),?(\d*) @@", line)
                    if match:
                        source_start = int(match.group(1))
                        source_len = int(match.group(2)) if match.group(2) else 1
                        target_start = int(match.group(3))
                        target_len = int(match.group(4)) if match.group(4) else 1
                        
                        current_hunk = {
                            "file_path": current_file.get("file_path", ""),
                            "source_start": source_start,
                            "source_length": source_len,
                            "target_start": target_start,
                            "target_length": target_len,
                        }
                        added_lines = []
                        removed_lines = []
                        hunk_lines = []
                
                elif not line.startswith("diff --git") and not line.startswith("---") and not line.startswith("+++"):
                    hunk_lines.append({"type": "context", "content": line})
                    if line.startswith("+"):
                        added_lines.append(current_hunk.get("target_start", 0) + len(added_lines))
                    elif line.startswith("-"):
                        removed_lines.append(current_hunk.get("source_start", 0) + len(removed_lines))
            
            # Save last file
            if current_file.get("file_path"):
                if current_hunk:
                    hunks.append(DiffHunk(
                        file_path=current_hunk.get("file_path", ""),
                        source_start=current_hunk.get("source_start", 0),
                        source_length=current_hunk.get("source_length", 0),
                        target_start=current_hunk.get("target_start", 0),
                        target_length=current_hunk.get("target_length", 0),
                        added_lines=tuple(added_lines),
                        removed_lines=tuple(removed_lines),
                        lines=tuple(hunk_lines),
                    ))
                files.append(DiffFile(
                    file_path=current_file["file_path"],
                    added_lines=tuple(added_lines),
                    removed_lines=tuple(removed_lines),
                    hunks=tuple(hunks),
                ))
            
            return DiffSnapshot(
                files=tuple(files),
                patches=patches,
                base_sha=base_sha,
                head_sha=head_sha,
            )
        except Exception as exc:
            raise RuntimeError(f"Failed to fetch diff: {exc}") from exc
        finally:
            client.close()
    
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
        
        client = self._get_client()
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
            raw = base64.b64decode(data["content"])
            content = raw.decode("utf-8")
            return content
        except UnicodeDecodeError:
            raise RepositoryNotFound(
                f"File is not a text file: {file_path}",
                details={"file": file_path, "sha": sha},
            )
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
        client = self._get_client()
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
        client = self._get_client()
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
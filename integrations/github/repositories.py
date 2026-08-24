"""GitHub repository provider implementation."""

from __future__ import annotations

import asyncio
import base64
from collections.abc import Sequence
from typing import Any

import requests  # type: ignore[import-untyped]

from core.errors import (
    AuthenticationFailure,
    CommitNotFound,
    FileNotFound,
    PartialBatchFailure,
    RateLimitExceeded,
    RemoteTimeout,
    RepositoryAccessDenied,
    RepositoryError,
    RepositoryNotFound,
    TreeNotFound,
    TreeTruncated,
)
from github import GithubException
from integrations.base import (
    RepositoryAcquisitionMode,
    RepositoryBlob,
    RepositoryCommit,
    RepositoryProvider,
    RepositoryTreeEntry,
)
from integrations.github.auth import GitHubAppAuth
from integrations.github.client import GitHubClient
from models.core import (
    DiffFile,
    DiffHunk,
    DiffSnapshot,
    RepositoryReference,
    RepositorySnapshot,
)


def _map_github_error(
    exc: Exception,
    context_msg: str,
) -> Exception:
    if isinstance(exc, (requests.Timeout, requests.ConnectTimeout)):
        return RemoteTimeout(f"Timeout: {context_msg} ({exc})")
    if isinstance(exc, requests.RequestException) and exc.response is not None:
        status_code = exc.response.status_code
        if status_code == 429:
            return RateLimitExceeded(f"Rate limit exceeded: {context_msg}")
        if status_code == 403:
            headers = exc.response.headers
            if (
                headers.get("X-RateLimit-Remaining") == "0"
                or "rate limit" in exc.response.text.lower()
            ):
                return RateLimitExceeded(f"Rate limit exceeded: {context_msg}")
            return AuthenticationFailure(f"Forbidden/Access denied: {context_msg}")
        if status_code == 401:
            return AuthenticationFailure(f"Unauthorized: {context_msg}")
        if status_code == 404:
            if "commit" in context_msg.lower():
                return CommitNotFound(f"Commit not found: {context_msg}")
            if "tree" in context_msg.lower():
                return TreeNotFound(f"Tree not found: {context_msg}")
            if "blob" in context_msg.lower() or "file" in context_msg.lower():
                return FileNotFound(f"File/Blob not found: {context_msg}")
            return RepositoryNotFound(f"Not found: {context_msg}")
    return RepositoryError(f"Error: {context_msg} ({exc})")


class GitHubRepositoryProvider(RepositoryProvider):
    """Implements RepositoryProvider for GitHub.

    Responsibilities:
    - fetch_repository()
    - fetch_tree()
    - fetch_diff()
    - fetch_file()
    - fetch_commit()
    """

    def __init__(
        self,
        auth: GitHubAppAuth | None = None,
        acquisition_mode: RepositoryAcquisitionMode | None = None,
    ) -> None:
        self.auth = auth
        from core.config import get_settings
        self.acquisition_mode = acquisition_mode or RepositoryAcquisitionMode(
            get_settings().REPOSITORY_ACQUISITION_MODE
        )

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

    async def fetch_repository(
        self, repo_ref: RepositoryReference
    ) -> RepositorySnapshot:
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

        Downloads the repository as a zipball archive or fetches it via Git-native
        API depending on configuration.

        Args:
            repo_ref: Repository reference
            sha: Commit SHA to fetch

        Returns:
            Repository snapshot at the specified commit
        """
        if self.acquisition_mode == RepositoryAcquisitionMode.GIT:
            print(f"[repositories] Fetching repository via Git-native path for {repo_ref.full_name} at {sha}")
            commit = await self.get_commit(repo_ref.full_name, sha)
            tree_entries = await self.get_tree(repo_ref.full_name, sha)
            
            # Extract only blob paths
            blob_paths = [entry.path for entry in tree_entries if entry.type == "blob"]
            
            # Fetch files
            blobs = await self.get_files(repo_ref.full_name, blob_paths, sha)
            
            # Reconstruct repository snapshot
            files = {}
            for blob in blobs:
                try:
                    files[blob.path] = blob.content.decode("utf-8")
                except (UnicodeDecodeError, UnicodeError):
                    continue  # skip binary files just like zipball
                    
            # Reconstruct tree dictionary to match zipball snapshot structure
            tree_data = {
                "sha": commit.sha,
                "tree": [
                    {
                        "path": entry.path,
                        "type": entry.type,
                        "sha": entry.sha,
                        "size": entry.size,
                    }
                    for entry in tree_entries
                ],
                "truncated": False,
            }
            
            return RepositorySnapshot(
                tree=tree_data,
                files=files,
                commit=commit.sha,
            )

        import io
        import zipfile

        print(
            f"[repositories] fetch_repository_at_sha: {repo_ref.full_name}, sha={sha}"
        )

        # Fetch commit info
        commit_info = await self.fetch_commit(repo_ref, sha)
        commit_sha = commit_info.get("sha", "")
        print(f"[repositories] Commit SHA: {commit_sha}")

        # Download the repository as a zipball at the specific commit
        client = self._get_client()
        try:
            url = f"/repos/{repo_ref.full_name}/zipball/{sha}"
            print(
                f"[repositories] Downloading zipball for {repo_ref.full_name} at {sha} (URL: {url})..."
            )

            print(f"[repositories] Sending GET request via client.get to {url}...")
            response = client.get(
                url,
                headers={"Accept": "application/vnd.github+json"},
                stream=True,
                allow_redirects=True,
                timeout=(10, 300),
            )
            print(f"[repositories] Response HTTP status: {response.status_code}")
            response.raise_for_status()

            content_bytes = bytearray()
            chunk_count = 0
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    content_bytes.extend(chunk)
                    chunk_count += 1

            zip_content = bytes(content_bytes)
            print(
                f"[repositories] Zipball download complete: {len(zip_content)} bytes ({len(zip_content) / (1024 * 1024):.2f} MB)"
            )
        except Exception as e:
            print(
                f"[repositories] ERROR during zipball download for {repo_ref.full_name} at {sha}: {e}"
            )
            raise
        finally:
            client.close()

        # Extract files from the zip archive
        files = {}
            tree_entries: list[dict[str, str]] = []

        with zipfile.ZipFile(io.BytesIO(zip_content)) as zf:
            all_names = zf.namelist()
            print(f"[repositories] Zipball entries: {len(all_names)}")
            if not all_names:
                return RepositorySnapshot(tree={}, files={}, commit=commit_sha)

            root_prefix = all_names[0]
            text_count = 0
            binary_count = 0
            for name in all_names:
                relative_name = (
                    name.removeprefix(root_prefix)
                )

                if not relative_name:
                    continue

                if zf.getinfo(name).is_dir():
                    tree_entries.append(
                        {
                            "path": relative_name.rstrip("/"),
                            "type": "tree",
                            "mode": "040000",
                        }
                    )
                else:
                    tree_entries.append(
                        {
                            "path": relative_name,
                            "type": "blob",
                            "mode": "100644",
                            "sha": "",
                        }
                    )

                    try:
                        raw = zf.read(name)
                        content = raw.decode("utf-8")
                        files[relative_name] = content
                        text_count += 1
                    except (UnicodeDecodeError, UnicodeError):
                        binary_count += 1
                        continue

        print(
            f"[repositories] Extracted: {text_count} text files, {binary_count} binary files skipped"
        )

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
                            hunks.append(
                                DiffHunk(
                                    file_path=current_hunk.get("file_path", ""),
                                    source_start=current_hunk.get("source_start", 0),
                                    source_length=current_hunk.get("source_length", 0),
                                    target_start=current_hunk.get("target_start", 0),
                                    target_length=current_hunk.get("target_length", 0),
                                    added_lines=tuple(added_lines),
                                    removed_lines=tuple(removed_lines),
                                    lines=tuple(hunk_lines),
                                )
                            )
                        files.append(
                            DiffFile(
                                file_path=current_file["file_path"],
                                added_lines=tuple(added_lines),
                                removed_lines=tuple(removed_lines),
                                hunks=tuple(hunks),
                            )
                        )

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
                        hunks.append(
                            DiffHunk(
                                file_path=current_hunk.get("file_path", ""),
                                source_start=current_hunk.get("source_start", 0),
                                source_length=current_hunk.get("source_length", 0),
                                target_start=current_hunk.get("target_start", 0),
                                target_length=current_hunk.get("target_length", 0),
                                added_lines=tuple(added_lines),
                                removed_lines=tuple(removed_lines),
                                lines=tuple(hunk_lines),
                            )
                        )

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

                elif (
                    not line.startswith("diff --git")
                    and not line.startswith("---")
                    and not line.startswith("+++")
                ):
                    hunk_lines.append({"type": "context", "content": line})
                    if line.startswith("+"):
                        added_lines.append(
                            current_hunk.get("target_start", 0) + len(added_lines)
                        )
                    elif line.startswith("-"):
                        removed_lines.append(
                            current_hunk.get("source_start", 0) + len(removed_lines)
                        )

            # Save last file
            if current_file.get("file_path"):
                if current_hunk:
                    hunks.append(
                        DiffHunk(
                            file_path=current_hunk.get("file_path", ""),
                            source_start=current_hunk.get("source_start", 0),
                            source_length=current_hunk.get("source_length", 0),
                            target_start=current_hunk.get("target_start", 0),
                            target_length=current_hunk.get("target_length", 0),
                            added_lines=tuple(added_lines),
                            removed_lines=tuple(removed_lines),
                            lines=tuple(hunk_lines),
                        )
                    )
                files.append(
                    DiffFile(
                        file_path=current_file["file_path"],
                        added_lines=tuple(added_lines),
                        removed_lines=tuple(removed_lines),
                        hunks=tuple(hunks),
                    )
                )

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
                raise RepositoryNotFound(
                    f"File not found: {file_path}",
                    details={"file": file_path, "sha": sha},
                )
            elif exc.status == 403:
                raise RepositoryAccessDenied(
                    f"Access denied to file: {file_path}", details={"file": file_path}
                )
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

    async def get_commit(
        self,
        repository: str,
        sha: str,
    ) -> RepositoryCommit:
        repo_ref = RepositoryReference.from_full_name(provider="github", full_name=repository)
        client = self._get_client()
        try:
            url = f"/repos/{repo_ref.full_name}/commits/{sha}"
            response = client.get(
                url,
                headers={"Accept": "application/vnd.github+json"},
                timeout=30,
            )
            response.raise_for_status()
            commit_data = response.json()
            return RepositoryCommit(
                sha=commit_data.get("sha", ""),
                repository=repository,
                message=commit_data.get("commit", {}).get("message"),
                author=commit_data.get("commit", {}).get("author", {}).get("name"),
            )
        except Exception as exc:  # noqa: BLE001 -- mapped into a domain error via _map_github_error
            raise _map_github_error(exc, f"fetch commit {sha} for {repository}")
        finally:
            client.close()

    async def get_tree(
        self,
        repository: str,
        sha: str,
    ) -> Sequence[RepositoryTreeEntry]:
        repo_ref = RepositoryReference.from_full_name(provider="github", full_name=repository)
        client = self._get_client()
        try:
            url = f"/repos/{repo_ref.full_name}/git/trees/{sha}"
            response = client.get(
                url,
                headers={"Accept": "application/vnd.github+json"},
                params={"recursive": "1"},
                timeout=30,
            )
            response.raise_for_status()
            tree_data = response.json()
            
            if tree_data.get("truncated", False):
                raise TreeTruncated(f"GitHub recursive tree response was truncated/incomplete for {repository} at {sha}")
                
            entries = []
            for item in tree_data.get("tree", []):
                item_type = item.get("type")
                if item_type in ("blob", "tree"):
                    entries.append(
                        RepositoryTreeEntry(
                            path=item["path"],
                            type=item_type,
                            sha=item["sha"],
                            size=item.get("size"),
                        )
                    )
            return entries
        except Exception as exc:
            if isinstance(exc, TreeTruncated):
                raise
            raise _map_github_error(exc, f"fetch tree {sha} for {repository}")
        finally:
            client.close()

    async def get_file(
        self,
        repository: str,
        path: str,
        ref: str,
    ) -> RepositoryBlob:
        from urllib.parse import quote
        
        repo_ref = RepositoryReference.from_full_name(provider="github", full_name=repository)
        client = self._get_client()
        try:
            encoded_path = quote(path, safe="/")
            url = f"/repos/{repo_ref.full_name}/contents/{encoded_path}"
            response = client.get(
                url,
                headers={"Accept": "application/vnd.github+json"},
                params={"ref": ref},
                timeout=30,
            )
            response.raise_for_status()
            meta = response.json()
            
            if isinstance(meta, list) or meta.get("type") != "file":
                from core.errors import FileNotFound
                raise FileNotFound(f"Path {path} is not a file in {repository} at {ref}")
                
            blob_sha = meta["sha"]
            size = meta["size"]
            
            blob_url = f"/repos/{repo_ref.full_name}/git/blobs/{blob_sha}"
            blob_response = client.get(
                blob_url,
                headers={"Accept": "application/vnd.github+json"},
                timeout=30,
            )
            blob_response.raise_for_status()
            blob_data = blob_response.json()
            
            content_bytes = base64.b64decode(blob_data["content"])
            return RepositoryBlob(
                path=path,
                sha=blob_sha,
                size=size,
                content=content_bytes,
            )
        except Exception as exc:
            from core.errors import FileNotFound
            if isinstance(exc, FileNotFound):
                raise
            raise _map_github_error(exc, f"fetch file {path} (ref: {ref}) from {repository}")
        finally:
            client.close()

    async def get_files(
        self,
        repository: str,
        paths: Sequence[str],
        ref: str,
    ) -> Sequence[RepositoryBlob]:
        import base64

        from core.config import get_settings
        from core.errors import FileNotFound
        
        repo_ref = RepositoryReference.from_full_name(provider="github", full_name=repository)
        unique_paths = sorted(set(paths))
        
        try:
            tree_entries = await self.get_tree(repository, ref)
        except Exception as exc:  # noqa: BLE001 -- mapped into a domain error via _map_github_error
            failures = {p: exc for p in unique_paths}
            raise PartialBatchFailure(successes=[], failures=failures)
            
        path_to_entry = {entry.path: entry for entry in tree_entries if entry.type == "blob"}
        
        settings = get_settings()
        limit = settings.GITHUB_MAX_CONCURRENT_BLOB_REQUESTS
        sem = asyncio.Semaphore(limit)
        
        async def fetch_blob(path: str, sha: str, size: int) -> RepositoryBlob:
            async with sem:
                def do_request():
                    client = self._get_client()
                    try:
                        blob_url = f"/repos/{repo_ref.full_name}/git/blobs/{sha}"
                        response = client.get(
                            blob_url,
                            headers={"Accept": "application/vnd.github+json"},
                            timeout=30,
                        )
                        response.raise_for_status()
                        return response.json()
                    finally:
                        client.close()
                        
                blob_data = await asyncio.to_thread(do_request)
                content_bytes = base64.b64decode(blob_data["content"])
                return RepositoryBlob(
                    path=path,
                    sha=sha,
                    size=size,
                    content=content_bytes,
                )
                
        async def fetch_blob_safe(path: str, sha: str, size: int) -> RepositoryBlob | Exception:
            try:
                return await fetch_blob(path, sha, size)
            except Exception as exc:  # noqa: BLE001 -- mapped into a domain error via _map_github_error
                return _map_github_error(exc, f"fetch blob {sha} for path {path}")
                
        tasks = []
        paths_to_fetch = []
        failures = {}
        
        for path in unique_paths:
            if path not in path_to_entry:
                failures[path] = FileNotFound(f"File not found in tree: {path}")
            else:
                entry = path_to_entry[path]
                tasks.append(fetch_blob_safe(path, entry.sha, entry.size or 0))
                paths_to_fetch.append(path)
                
        results = await asyncio.gather(*tasks) if tasks else []
        
        successes = []
        for path, res in zip(paths_to_fetch, results):
            if isinstance(res, Exception):
                failures[path] = res
            else:
                successes.append(res)
                
        # Deterministic sorting by path for successes
        successes.sort(key=lambda b: b.path)
        
        # Logging
        retrieved_bytes = sum(len(b.content) for b in successes)
        print("[repositories] Source: github_git")
        print(f"[repositories] Repository: {repository}")
        print(f"[repositories] Commit: {ref}")
        print(f"[repositories] Tree entries: {len(tree_entries)}")
        print(f"[repositories] Requested files: {len(unique_paths)}")
        print(f"[repositories] Retrieved files: {len(successes)}")
        print(f"[repositories] Retrieved bytes: {retrieved_bytes}")
        print("[repositories] ZIPBALL: false")
        
        if failures:
            raise PartialBatchFailure(successes=successes, failures=failures)
            
        return successes

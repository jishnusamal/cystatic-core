"""GitHub Publisher for posting PR comments.

Publishes validated markdown comments to GitHub pull requests.
Consumes only the final markdown - never talks to LLM or compiler.
"""

from __future__ import annotations

from typing import Any

from integrations.github.client import GitHubClient


class GitHubPublisher:
    """
    Publishes markdown comments to GitHub pull requests.
    
    Responsibilities:
    - Post comments to PRs
    - Handle authentication
    - Manage errors
    
    Never talks to LLM or compiler. Only consumes markdown.
    """
    
    def __init__(self, token: str | None = None):
        """
        Initialize GitHub publisher.
        
        Args:
            token: GitHub authentication token. If None, uses unauthenticated client.
        """
        self.token = token
        self.client = GitHubClient(token=token)
    
    async def publish_comment(
        self,
        repository: str,
        pr_number: int,
        markdown: str,
    ) -> dict[str, Any]:
        """
        Publish a markdown comment to a GitHub pull request.
        
        Args:
            repository: Repository in format "owner/repo".
            pr_number: Pull request number.
            markdown: The markdown comment to post.
            
        Returns:
            Dictionary with publication result:
                - success (bool): Whether publication succeeded
                - comment_id (str | None): GitHub comment ID if successful
                - error (str | None): Error message if failed
        """
        try:
            # Post comment to PR
            response = self.client.post(
                f"/repos/{repository}/issues/{pr_number}/comments",
                json={"body": markdown},
            )
            response.raise_for_status()
            
            comment_data = response.json()
            
            return {
                "success": True,
                "comment_id": str(comment_data.get("id", "")),
                "error": None,
            }
            
        except Exception as exc:
            return {
                "success": False,
                "comment_id": None,
                "error": str(exc),
            }
        finally:
            self.client.close()
    
    def publish_comment_sync(
        self,
        repository: str,
        pr_number: int,
        markdown: str,
    ) -> dict[str, Any]:
        """
        Synchronous version of publish_comment.
        
        Args:
            repository: Repository in format "owner/repo".
            pr_number: Pull request number.
            markdown: The markdown comment to post.
            
        Returns:
            Dictionary with publication result.
        """
        try:
            # Post comment to PR
            response = self.client.post(
                f"/repos/{repository}/issues/{pr_number}/comments",
                json={"body": markdown},
            )
            response.raise_for_status()
            
            comment_data = response.json()
            
            return {
                "success": True,
                "comment_id": str(comment_data.get("id", "")),
                "error": None,
            }
            
        except Exception as exc:
            return {
                "success": False,
                "comment_id": None,
                "error": str(exc),
            }
        finally:
            self.client.close()
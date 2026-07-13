"""GitHub App authentication.

Provides JWT-based authentication for GitHub Apps and installation access tokens.
"""

from __future__ import annotations

import time
from typing import Any

import jwt
from github import Auth, Github, GithubException

from runtime.errors import RepositoryNotInstalled


class GitHubAppAuth:
    """
    GitHub App authentication handler.
    
    Manages JWT token generation and installation access token retrieval.
    """
    
    def __init__(
        self,
        app_id: str,
        private_key: str,
        client_secret: str | None = None,
    ) -> None:
        """
        Initialize GitHub App authentication.
        
        Args:
            app_id: GitHub App ID
            private_key: GitHub App private key (PEM format)
            client_secret: GitHub App client secret (optional, for OAuth)
        """
        self.app_id = app_id
        self.private_key = private_key
        self.client_secret = client_secret
        self._jwt_cache: tuple[str, float] | None = None  # (token, expiry)
    
    def get_jwt_token(self, expiration_seconds: int = 600) -> str:
        """
        Generate a JWT token for GitHub App authentication.
        
        Args:
            expiration_seconds: Token expiration time in seconds (max 600)
            
        Returns:
            JWT token string
        """
        # Check cache
        if self._jwt_cache is not None:
            token, expiry = self._jwt_cache
            if time.time() < expiry - 60:  # Refresh 1 minute before expiry
                return token
        
        # Generate new token
        now = int(time.time())
        payload = {
            "iat": now,
            "exp": now + min(expiration_seconds, 600),
            "iss": self.app_id,
        }
        
        token = jwt.encode(payload, self.private_key, algorithm="RS256")
        
        # Cache token
        self._jwt_cache = (token, now + expiration_seconds)
        
        return token
    
    def get_installation_access_token(
        self,
        installation_id: int,
        jwt_token: str | None = None,
    ) -> str:
        """
        Get an installation access token for a specific installation.
        
        Args:
            installation_id: GitHub App installation ID
            jwt_token: JWT token (generates new one if not provided)
            
        Returns:
            Installation access token
            
        Raises:
            RepositoryNotInstalled: If token retrieval fails
        """
        if jwt_token is None:
            jwt_token = self.get_jwt_token()
        
        # Use PyGithub to get installation token
        try:
            # Create authenticated client with JWT
            auth = Auth.AppAuth(
                app_id=self.app_id,
                private_key=self.private_key,
            )
            client = Github(auth=auth)
            
            # Get installation token
            installation = client.get_installation(installation_id)
            token = installation.get_access_token()
            
            client.close()
            
            return token.token
            
        except GithubException as exc:
            raise RepositoryNotInstalled(
                f"Failed to get installation access token: {exc.data.get('message', str(exc))}",
                details={
                    "installation_id": installation_id,
                    "status": exc.status,
                },
            ) from exc
    
    def get_authenticated_client(
        self,
        installation_id: int,
    ) -> Github:
        """
        Get an authenticated GitHub client for a specific installation.
        
        Args:
            installation_id: GitHub App installation ID
            
        Returns:
            Authenticated Github client
        """
        jwt_token = self.get_jwt_token()
        access_token = self.get_installation_access_token(installation_id, jwt_token)
        
        return Github(auth=Auth.Token(access_token))
    
    def get_authenticated_bot(
        self,
        installation_id: int,
    ) -> "GitHubBot":
        """
        Get an authenticated GitHubBot for a specific installation.
        
        Args:
            installation_id: GitHub App installation ID
            
        Returns:
            Authenticated GitHubBot instance
        """
        from source_adapters.github.bot import GitHubBot
        
        jwt_token = self.get_jwt_token()
        access_token = self.get_installation_access_token(installation_id, jwt_token)
        
        return GitHubBot(token=access_token)


# Import here to avoid circular dependency
from source_adapters.github.bot import GitHubBot
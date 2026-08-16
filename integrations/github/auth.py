"""GitHub App authentication."""

from __future__ import annotations

import time

import jwt

from github import Auth, Github


class GitHubAppAuth:
    """GitHub App authentication handler.

    Only GitHub App authentication.
    Responsibilities:
    - JWT generation
    - Installation token exchange

    Nothing else.
    """

    def __init__(
        self, app_id: str, private_key: str, client_secret: str | None = None
    ) -> None:
        self.app_id = app_id
        self.private_key = private_key
        self.client_secret = client_secret
        self._token_cache: dict[int, tuple[str, float]] = {}

    def generate_jwt(self) -> str:
        """Generate a JWT for GitHub App authentication.

        Returns:
            JWT token
        """
        now = int(time.time())
        payload = {
            "iat": now,
            "exp": now + (10 * 60),  # 10 minutes
            "iss": self.app_id,
        }
        return jwt.encode(payload, self.private_key, algorithm="RS256")

    async def get_installation_token(self, installation_id: int) -> str:
        """Get an installation token.

        Args:
            installation_id: GitHub App installation ID

        Returns:
            Installation access token
        """
        # Check cache
        if installation_id in self._token_cache:
            token, expires_at = self._token_cache[installation_id]
            if time.time() < expires_at - 60:  # 1 minute buffer
                return token

        # Generate new token
        jwt_token = self.generate_jwt()
        github = Github(auth=Auth.AppAuth(self.app_id, self.private_key))

        try:
            installation = github.get_installation()  # type: ignore[attr-defined]
            token = installation.get_access_token()
            expires_at = time.time() + (
                60 * 60
            )  # 1 hour (GitHub tokens expire in 1 hour)
            self._token_cache[installation_id] = (token, expires_at)
            return token  # type: ignore[no-any-return]
        finally:
            github.close()

    async def authenticate(self, installation_id: str) -> str:
        """Get an authentication token for the installation.

        Args:
            installation_id: Installation identifier

        Returns:
            Authentication token
        """
        return await self.get_installation_token(int(installation_id))

    async def get_authenticated_bot(self, installation_id: int | None = None) -> Github:
        """Get an authenticated GitHub client.

        Args:
            installation_id: Installation ID (optional, uses app JWT if not provided)

        Returns:
            Authenticated GitHub client
        """
        if installation_id:
            token = await self.get_installation_token(installation_id)
            return Github(auth=Auth.Token(token))
        else:
            jwt_token = self.generate_jwt()
            return Github(auth=Auth.JWT(jwt_token))  # type: ignore[abstract,call-arg]

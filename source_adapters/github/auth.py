"""GitHub App authentication helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
import requests


@dataclass(frozen=True)
class GitHubAppCredentials:
    app_id: str = ""
    private_key: str = ""
    access_token: str = ""
    client_secret: str = ""
    api_base_url: str = "https://api.github.com"


def _normalize_private_key(private_key: str) -> str:
    return private_key.replace("\\n", "\n").strip()


def build_app_jwt(app_id: str, private_key: str) -> str:
    if not app_id:
        raise ValueError("GitHub App ID is required to build a JWT")
    if not private_key:
        raise ValueError("GitHub private key is required to build a JWT")

    now = datetime.now(timezone.utc)
    payload = {
        "iat": int((now - timedelta(seconds=60)).timestamp()),
        "exp": int((now + timedelta(minutes=9)).timestamp()),
        "iss": app_id,
    }
    return jwt.encode(payload, _normalize_private_key(private_key), algorithm="RS256")


def exchange_installation_token(
    *,
    app_id: str,
    private_key: str,
    installation_id: int,
    api_base_url: str = "https://api.github.com",
) -> str:
    jwt_token = build_app_jwt(app_id, private_key)
    url = f"{api_base_url.rstrip('/')}/app/installations/{installation_id}/access_tokens"

    response = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {jwt_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        timeout=30,
    )
    response.raise_for_status()

    data: dict[str, Any] = response.json()
    token = data.get("token")
    if not token:
        raise ValueError("GitHub installation token response did not include a token")
    return str(token)


def get_installation_token(
    app_id: str,
    private_key: str,
    installation_id: int,
) -> str:
    """Get GitHub App installation token. This is the ONLY path for GitHub App webhook operations.
    
    Never uses personal access tokens—only installation-scoped tokens.
    """
    if not app_id:
        raise ValueError("GitHub App ID is required for GitHub App installation token flow")
    if not private_key:
        raise ValueError("GitHub App private key is required for GitHub App installation token flow")
    if not installation_id:
        raise ValueError("Installation ID is required for GitHub App installation token flow")

    return exchange_installation_token(
        app_id=app_id,
        private_key=private_key,
        installation_id=installation_id,
    )


def resolve_github_token(
    credentials: GitHubAppCredentials,
    installation_id: int | None = None,
) -> str:
    """Legacy token resolution for backwards compatibility.
    
    DO NOT USE for GitHub App webhook operations. Use get_installation_token() instead.
    """
    if credentials.access_token:
        return credentials.access_token

    if credentials.app_id and credentials.private_key and installation_id is not None:
        return exchange_installation_token(
            app_id=credentials.app_id,
            private_key=credentials.private_key,
            installation_id=installation_id,
            api_base_url=credentials.api_base_url,
        )

    raise ValueError("GitHub credentials are not configured")

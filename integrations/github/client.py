"""Thin HTTP wrapper for GitHub API."""

from __future__ import annotations

from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class GitHubClient:
    """Thin HTTP wrapper for GitHub API.

    No business logic.
    """

    def __init__(
        self, token: str | None = None, base_url: str = "https://api.github.com"
    ) -> None:
        self.token = token or ""
        self.base_url = base_url.rstrip("/")
        self._session = requests.Session()

        # Configure retries
        retry = Retry(
            total=3,
            connect=3,
            read=3,
            backoff_factor=1,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset(["GET", "POST", "PATCH", "DELETE"]),
        )
        adapter = HTTPAdapter(max_retries=retry)
        self._session.mount("https://", adapter)
        self._session.mount("http://", adapter)

    def close(self) -> None:
        """Close the session."""
        self._session.close()

    def get(self, path: str, **kwargs: Any) -> requests.Response:
        """Make a GET request.

        Args:
            path: API path
            **kwargs: Additional request arguments

        Returns:
            Response object
        """
        url = f"{self.base_url}{path}"
        headers = kwargs.pop("headers", {})
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return self._session.get(url, headers=headers, **kwargs)

    def post(self, path: str, **kwargs: Any) -> requests.Response:
        """Make a POST request.

        Args:
            path: API path
            **kwargs: Additional request arguments

        Returns:
            Response object
        """
        url = f"{self.base_url}{path}"
        headers = kwargs.pop("headers", {})
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return self._session.post(url, headers=headers, **kwargs)

    def patch(self, path: str, **kwargs: Any) -> requests.Response:
        """Make a PATCH request.

        Args:
            path: API path
            **kwargs: Additional request arguments

        Returns:
            Response object
        """
        url = f"{self.base_url}{path}"
        headers = kwargs.pop("headers", {})
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return self._session.patch(url, headers=headers, **kwargs)

    def delete(self, path: str, **kwargs: Any) -> requests.Response:
        """Make a DELETE request.

        Args:
            path: API path
            **kwargs: Additional request arguments

        Returns:
            Response object
        """
        url = f"{self.base_url}{path}"
        headers = kwargs.pop("headers", {})
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return self._session.delete(url, headers=headers, **kwargs)

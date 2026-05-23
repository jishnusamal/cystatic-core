"""GitHub webhook verification helpers."""

from __future__ import annotations

import hashlib
import hmac


def verify_github_webhook_signature(
    payload: bytes,
    signature: str | None,
    secret: str | None,
) -> bool:
    if not secret:
        return True

    if not signature or not signature.startswith("sha256="):
        return False

    expected_signature = "sha256=" + hmac.new(
        secret.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected_signature, signature)

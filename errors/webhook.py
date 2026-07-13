"""Webhook errors."""

from __future__ import annotations

from typing import Any


class WebhookError(Exception):
    """Base webhook error."""
    
    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.details = details or {}


class WebhookVerificationError(WebhookError):
    """Webhook signature verification failed."""
    pass
from __future__ import annotations

import os
from typing import Any
import sentry_sdk
from fastapi import FastAPI, Request
from sentry_sdk.integrations.fastapi import FastApiIntegration
import hashlib

class SentryInstrumentation:
    def __init__(self, settings: Any) -> None:
        self.dsn = settings.SENTRY_DSN
        self.enabled = bool(settings.SENTRY_DSN)
        self.app_env = settings.APP_ENV
        self.app_version = settings.APP_VERSION

    def init(self) -> None:
        if not self.enabled:
            print("Sentry disabled: SENTRY_DSN is missing")
            return
        
        if self.app_env != "production":
            print(f"Sentry disabled in {self.app_env} environment")
            return 

        sentry_sdk.init(
            dsn=self.dsn,
            integrations=[FastApiIntegration()],
            environment=self.app_env or "production",
            release=self.app_version or "unknown",
            traces_sample_rate=0.0,
            send_default_pii=False,
        )

    def set_context(
        self,
        *,
        org_id: str | None = None,
        repo: str | None = None,
        pr_number: int | None = None,
        provider: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        if not self.enabled:
            return

        if org_id:
            sentry_sdk.set_user({"id": org_id})
            sentry_sdk.set_tag("org_id", org_id)

        if repo:
            sentry_sdk.set_tag("repo", repo)

        if provider:
            sentry_sdk.set_tag("provider", provider)

        if pr_number is not None:
            sentry_sdk.set_tag("pr_number", str(pr_number))

        sentry_sdk.set_context(
            "pr_analysis",
            {
                "org_id": org_id,
                "repo": repo,
                "pr_number": pr_number,
                "provider": provider,
                **(extra or {}),
            },
        )

    def capture_exception(self, exc: Exception, **extra: Any) -> None:
        if not self.enabled:
            return

        with sentry_sdk.push_scope() as scope:
            for key, value in extra.items():
                scope.set_extra(key, value)
            sentry_sdk.capture_exception(exc)

    def capture_warning(self, message: str, **extra: Any) -> None:
        if not self.enabled:
            return

        with sentry_sdk.push_scope() as scope:
            for key, value in extra.items():
                scope.set_extra(key, value)
            sentry_sdk.capture_message(message, level="warning")


    def attach_middleware(self, app: FastAPI) -> None:
        if not self.enabled:
            return

        @app.middleware("http")
        async def sentry_context_middleware(request: Request, call_next):
            # Extract API key
            api_key = request.headers.get("x-api-key")

            if api_key:
                # ⚠️ NEVER send raw API key to Sentry
                org_id = self._hash_api_key(api_key)

                sentry_sdk.set_user({"id": org_id})
                sentry_sdk.set_tag("org_id", org_id)
                sentry_sdk.set_tag("endpoint", request.url.path)
                sentry_sdk.set_tag("method", request.method)

            response = await call_next(request)
            return response
        
    def _hash_api_key(self, api_key: str) -> str:
        return hashlib.sha256(api_key.encode()).hexdigest()[:16]
    
    
# Example usage:
#
# from fastapi import FastAPI
# from instrumentation.sentry import init_sentry, attach_request_context
#
# init_sentry()
# app = FastAPI()
# attach_request_context(app)
#
#
# In a route or service:
#
# from instrumentation.sentry import set_sentry_context, capture_exception, capture_warning
#
# set_sentry_context(
#     org_id="org_123",
#     repo="factor-api/demo",
#     pr_number=42,
#     provider="github",
# )
#
# try:
#     ...
# except Exception as exc:
#     capture_exception(exc)
#     raise
#
# capture_warning("Empty analysis result", phase="post_analysis")
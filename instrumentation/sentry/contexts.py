from typing import Any

from fastapi import Request
from schemas import AnalyzeRequest
from . import sentry


def sentry_pr_context(request: Request, body: AnalyzeRequest) -> None:
    org_id = getattr(request.state, "org_id", None)

    if hasattr(sentry, 'set_context'):
        sentry.set_context(
            org_id=org_id,
            repo=body.repo,
            pr_number=body.pr_number,
            provider="github",
        )

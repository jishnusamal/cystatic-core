from api.settings import get_settings
from .sentry import SentryInstrumentation

settings = get_settings()

sentry = SentryInstrumentation(settings)
sentry.init()

from .contexts import sentry_pr_context

__all__ = ["sentry", "sentry_pr_context"]

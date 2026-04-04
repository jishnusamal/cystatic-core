# from .sentry import SentryInstrumentation

# __all__ = ["SentryInstrumentation"]

# instrumentation/__init__.py

from .sentry import SentryInstrumentation
from api.settings import get_settings

settings = get_settings()

sentry = SentryInstrumentation(settings)
sentry.init()
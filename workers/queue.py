"""Dramatiq broker and queue setup.

Configures the Redis-backed Dramatiq broker used for all background tasks.
"""

from __future__ import annotations

import dramatiq
from dramatiq.brokers.redis import RedisBroker
from dramatiq.middleware import CurrentMessage

from core.config import get_settings


def create_broker() -> RedisBroker:
    """Create and configure the Dramatiq Redis broker."""
    settings = get_settings()

    # Parse Redis URL from Upstash REST URL
    # Upstash Redis REST URL format: https://<host>
    # We use the standard Redis URL for the broker
    redis_url = settings.UPSTASH_REDIS_REST_URL

    broker = RedisBroker(url=redis_url)
    broker.add_middleware(CurrentMessage())
    return broker


broker = create_broker()
dramatiq.set_broker(broker)

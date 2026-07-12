from __future__ import annotations

import os
import logging

from dramatiq.brokers.redis import RedisBroker

logger = logging.getLogger(__name__)


def _build_redis_url() -> str:
    # Prefer explicit REDIS_URL if provided
    explicit = os.getenv("REDIS_URL")
    if explicit:
        return explicit

    token = os.getenv("UPSTASH_REDIS_REST_TOKEN")
    rest_url = os.getenv("UPSTASH_REDIS_REST_URL")
    if token and rest_url:
        # Try to construct a rediss url for Upstash from the REST host and token.
        # This is best-effort: Upstash usually provides a separate Redis URL, but
        # when only REST values are present we attempt to derive a TLS redis URL.
        host = rest_url.replace("https://", "").replace("http://", "").strip().rstrip("/")
        redis_url = f"rediss://default:{token}@{host}:6379"
        logger.info("Using derived Redis URL for dramatiq broker")
        return redis_url

    # Default to localhost redis
    return os.getenv("REDIS_URL", "redis://localhost:6379")


REDIS_URL = _build_redis_url()

# Create Redis broker for dramatiq
broker = RedisBroker(url=REDIS_URL)

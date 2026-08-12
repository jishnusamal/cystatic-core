"""Core database configuration stub.

Provides Tortoise ORM connection setup for the Factor platform.
"""

from __future__ import annotations

# TODO: Implement Tortoise ORM connection setup
# from tortoise import Tortoise
# from core.config import get_settings
#
# TORTOISE_ORM = {
#     "connections": {"default": get_settings().DATABASE_URL},
#     "apps": {
#         "models": {
#             "models": ["models.auth", "models.analysis", "models.billing"],
#             "default_connection": "default",
#         }
#     },
# }
#
# async def init_db() -> None:
#     """Initialize Tortoise ORM connection."""
#     await Tortoise.init(config=TORTOISE_ORM)
#
# async def close_db() -> None:
#     """Close Tortoise ORM connection."""
#     await Tortoise.close_connections()

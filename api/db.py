from api.settings import get_settings
from urllib.parse import urlparse

settings = get_settings()


TORTOISE_ORM = {
    "connections": {
        "default": settings.database_url,  # pooled Neon URL for runtime
    },
    "apps": {
        "models": {
            "models": [
                "api.models",
            ],
            "default_connection": "default",
        }
    },
}
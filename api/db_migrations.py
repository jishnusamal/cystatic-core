from api.settings import get_settings

settings = get_settings()

TORTOISE_ORM_MIGRATIONS = {
    "connections": {
        "default": settings.database_url_direct,  # direct Neon URL
    },
    "apps": {
        "models": {
            "models": ["api.models"],
            "default_connection": "default",
            "migrations": "api.migrations",
        }
    },
}
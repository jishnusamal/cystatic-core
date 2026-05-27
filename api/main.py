from __future__ import annotations

from fastapi import FastAPI
from tortoise.contrib.fastapi import register_tortoise

from api.admin.urls import router as admin_router
from api.db import TORTOISE_ORM
from api.settings import get_settings
from api.user.urls import router as user_router
from instrumentation import sentry

settings = get_settings()
app = FastAPI(title="Factor", version=settings.app_version or "0.1.0")
sentry.attach_middleware(app)

app.include_router(admin_router)
app.include_router(user_router)

register_tortoise(
    app,
    config=TORTOISE_ORM,
    generate_schemas=False,
    add_exception_handlers=True,
)
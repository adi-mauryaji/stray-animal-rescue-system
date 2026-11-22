"""FastAPI application factory (blueprint 12.1).

create_app() builds a new app on every call, so each test gets its own
app and nothing is shared between them.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response

from rescue.platform.db import database_is_ready, dispose_engine, get_engine


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
    yield  # the app serves requests while paused here
    await dispose_engine()  # shutdown: close pooled database connections


def create_app() -> FastAPI:
    app = FastAPI(title="Stray Animal Rescue API", version="0.1.0", lifespan=lifespan)

    @app.get("/health/live", tags=["health"])
    def live() -> dict[str, str]:
        """The process is running. Checks nothing else (blueprint 23)."""
        return {"status": "ok"}

    @app.get("/health/ready", tags=["health"])
    async def ready(response: Response) -> dict[str, str]:
        """Dependencies answer; today only the database (blueprint 23)."""
        if await database_is_ready(get_engine()):
            return {"status": "ok", "database": "ok"}
        response.status_code = 503  # Service Unavailable
        return {"status": "unavailable", "database": "down"}

    return app

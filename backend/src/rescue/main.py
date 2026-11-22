"""FastAPI application factory (blueprint 12.1).

create_app() builds a new app on every call, so each test gets its own
app and nothing is shared between them.
"""

from fastapi import FastAPI


def create_app() -> FastAPI:
    app = FastAPI(title="Stray Animal Rescue API", version="0.1.0")

    @app.get("/health/live", tags=["health"])
    def live() -> dict[str, str]:
        """The process is running. Checks nothing else (blueprint 23)."""
        return {"status": "ok"}

    return app

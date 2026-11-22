"""Readiness: /health/ready tells whether the database answers (blueprint 23).

The first test is an integration test: it needs `docker compose up -d db`
and backend/.env, and it must run from backend/ (where .env lives).
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from rescue.main import create_app
from rescue.platform.config import get_settings


@pytest.fixture(autouse=True)
def fresh_settings() -> Iterator[None]:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_ready_when_database_answers() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_not_ready_when_database_is_unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    # Port 1 on this machine refuses connections immediately.
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://rescue:x@127.0.0.1:1/rescue")

    with TestClient(create_app()) as client:
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable", "database": "down"}

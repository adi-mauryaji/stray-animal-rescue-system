"""Settings come from the environment and refuse to start without a database URL."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from rescue.platform.config import get_settings

URL = "postgresql+asyncpg://rescue:s3cret@db:5432/rescue"


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)  # empty folder: no .env file, only real env vars count
    get_settings.cache_clear()  # every test builds its own Settings


def test_reads_database_url_and_hides_password(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", URL)

    settings = get_settings()

    assert settings.database_url.get_secret_value() == URL
    assert "s3cret" not in repr(settings)


def test_missing_database_url_stops_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(ValidationError):
        get_settings()

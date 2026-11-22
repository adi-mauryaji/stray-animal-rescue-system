"""Application settings from environment variables (blueprint 12.6).

This is the only module that reads the environment. A missing required
value stops the app at startup instead of failing later at first use.
"""

from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Real environment variables win over the .env file; unknown keys are ignored.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: Literal["dev", "test", "prod"] = "dev"
    # Required. SecretStr keeps the password out of logs and error messages.
    database_url: SecretStr


@lru_cache
def get_settings() -> Settings:
    """One Settings object per process, created on first use."""
    return Settings()  # pyright: ignore[reportCallIssue]  # values come from the env

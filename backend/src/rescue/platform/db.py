"""Database engine and readiness check (blueprint 11.3, 12.1, 23).

One async engine per process. It keeps a small pool of open connections,
so requests reuse them instead of opening a new one each time.
"""

from functools import lru_cache

from sqlalchemy import MetaData, text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from rescue.platform.config import get_settings

# Names Alembic gives indexes and constraints, so they match the hand-written
# DDL of blueprint 11.1 instead of SQLAlchemy's defaults.
NAMING_CONVENTION = {
    "ix": "%(table_name)s_%(column_0_N_name)s_idx",
    "uq": "%(table_name)s_%(column_0_N_name)s_key",
    "ck": "%(table_name)s_%(constraint_name)s_check",
    "fk": "%(table_name)s_%(column_0_N_name)s_fkey",
    "pk": "%(table_name)s_pkey",
}


class Base(DeclarativeBase):
    """Every module's models.py inherits from this (blueprint 12.1).

    Alembic reads `Base.metadata` to compare models against the database.
    """

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


@lru_cache
def get_engine() -> AsyncEngine:
    url = get_settings().database_url.get_secret_value()
    return create_async_engine(
        url,
        pool_size=5,  # connection budget per API process (blueprint 11.3)
        max_overflow=5,  # extra connections allowed during short bursts
        pool_pre_ping=True,  # test a pooled connection before handing it out
        connect_args={"timeout": 2},  # asyncpg: give up connecting after 2 s
    )


async def database_is_ready(engine: AsyncEngine) -> bool:
    """True when the database answers a trivial query."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:  # any failure means "not ready"; logging comes with telemetry
        return False
    return True


async def dispose_engine() -> None:
    """Close pooled connections at shutdown, if an engine was ever created."""
    if get_engine.cache_info().currsize:
        await get_engine().dispose()
        get_engine.cache_clear()

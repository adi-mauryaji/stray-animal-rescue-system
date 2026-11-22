"""Database engine and readiness check (blueprint 11.3, 12.1, 23).

One async engine per process. It keeps a small pool of open connections,
so requests reuse them instead of opening a new one each time.
"""

from functools import lru_cache

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from rescue.platform.config import get_settings


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

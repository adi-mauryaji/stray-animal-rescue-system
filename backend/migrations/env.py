"""Alembic environment (blueprint Appendix E.4).

Run it from `backend/`, because that is where `.env` lives:
    uv run alembic upgrade head

The database URL comes from Settings only — no fallback password here and
none in alembic.ini. Offline mode (`--sql`) prints the SQL without connecting.
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from geoalchemy2 import alembic_helpers
from sqlalchemy import Connection
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from rescue.platform.config import get_settings
from rescue.platform.db import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)  # logging settings from alembic.ini

# What `--autogenerate` compares the live database against. Models arrive module
# by module (blueprint 12.1), so a schema without models looks "extra" to
# Alembic and it would offer to drop it: write those migrations by hand until
# the models exist.
target_metadata = Base.metadata


def database_url() -> str:
    """The URL from Settings; a missing DATABASE_URL stops us here, not mid-migration."""
    return get_settings().database_url.get_secret_value()


def run_migrations_offline() -> None:
    """Render SQL to stdout instead of running it (`alembic upgrade head --sql`)."""
    context.configure(
        url=database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_schemas=True,  # one schema per module (blueprint 11.0)
        compare_type=True,
        # GeoAlchemy2 helpers: skip PostGIS's own tables (spatial_ref_sys), add
        # the spatial operations, and import geography types in new revisions.
        include_object=alembic_helpers.include_object,
        process_revision_directives=alembic_helpers.writer,
        render_item=alembic_helpers.render_item,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """The synchronous part Alembic needs, handed a connection by run_sync()."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_schemas=True,
        compare_type=True,
        include_object=alembic_helpers.include_object,
        process_revision_directives=alembic_helpers.writer,
        render_item=alembic_helpers.render_item,
    )
    with context.begin_transaction():  # all migrations in one transaction
        context.run_migrations()


async def run_migrations_online() -> None:
    """One short-lived connection (NullPool: no pool to leave behind)."""
    engine = create_async_engine(database_url(), poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            await connection.run_sync(do_run_migrations)
    finally:
        await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())

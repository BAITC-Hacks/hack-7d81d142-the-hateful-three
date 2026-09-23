"""Alembic environment using the application's DATABASE_URL and model metadata."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection, pool

from backend.core.database import create_db_engine, get_database_url
from backend.models import Base


config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    # Pass a URL object directly: percent-encoded passwords must not be processed
    # by ConfigParser's interpolation or rendered with a hidden password.
    context.configure(
        url=get_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def migrate_connection(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        render_as_batch=connection.dialect.name == "sqlite",
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # Tests and embedding callers may supply an already-open connection.
    connection = config.attributes.get("connection")
    if connection is not None:
        migrate_connection(connection)
        return

    engine = create_db_engine(poolclass=pool.NullPool)
    try:
        with engine.connect() as connection:
            migrate_connection(connection)
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

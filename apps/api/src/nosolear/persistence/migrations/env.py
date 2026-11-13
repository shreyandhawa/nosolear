"""Alembic environment.

`upgrade_to_head` hands in an open connection; the CLI (`alembic.ini`) builds its own engine
from Settings.
"""

from alembic import context
from sqlalchemy import Connection

from nosolear.persistence.db import create_engine_for, foreign_keys_off
from nosolear.persistence.models import metadata
from nosolear.settings import Settings


def _run(connection: Connection) -> None:
    # SQLite cannot alter columns or add constraints in place; batch mode rebuilds the table.
    context.configure(connection=connection, target_metadata=metadata, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    raise RuntimeError("offline migrations are not supported")

supplied = context.config.attributes.get("connection")
if supplied is not None:
    _run(supplied)
else:
    engine = create_engine_for(Settings().database_url)
    with engine.connect() as connection, foreign_keys_off(connection), connection.begin():
        _run(connection)
    engine.dispose()

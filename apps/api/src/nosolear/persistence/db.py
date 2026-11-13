"""Engine construction and migrations."""

from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, Engine, create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.engine.interfaces import DBAPIConnection
from sqlalchemy.pool import ConnectionPoolEntry

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def _set_pragmas(dbapi_connection: DBAPIConnection, _record: ConnectionPoolEntry) -> None:
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
    finally:
        cursor.close()


def create_engine_for(url: str) -> Engine:
    database = make_url(url).database
    if database and database != ":memory:":
        Path(database).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(url)
    event.listen(engine, "connect", _set_pragmas)
    return engine


@contextmanager
def foreign_keys_off(connection: Connection) -> Generator[None]:
    """Turn foreign-key enforcement off for the duration, as a table rebuild needs.

    `PRAGMA foreign_keys` is a no-op inside a transaction, so it is set before one begins and
    restored after the block, even when the block fails.
    """
    connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
    connection.commit()
    try:
        yield
    finally:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        connection.commit()


def _check_foreign_keys(connection: Connection) -> None:
    if connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall():
        raise RuntimeError("the migration left foreign key violations")


def upgrade_to_head(engine: Engine, revision: str = "head") -> None:
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    with engine.connect() as connection, foreign_keys_off(connection), connection.begin():
        config.attributes["connection"] = connection
        command.upgrade(config, revision)
        _check_foreign_keys(connection)

"""`BEGIN IMMEDIATE` transactions for SQLite, shared by the usage ledger and the job queue.

pysqlite does not begin a transaction before a SELECT, so the BEGIN is issued by hand. The write
lock is then taken before any read in the block, so a read-then-write cannot interleave.
"""

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import Engine
from sqlalchemy.engine import Connection


@contextmanager
def immediate(engine: Engine) -> Generator[Connection]:
    """A connection inside `BEGIN IMMEDIATE`: commit on success, roll back on any error."""
    conn = engine.connect()
    try:
        conn.exec_driver_sql("BEGIN IMMEDIATE")
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()

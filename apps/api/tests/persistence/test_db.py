from dataclasses import replace
from pathlib import Path

import pytest
from factories import SAMPLE_OBS
from sqlalchemy import Engine, inspect, text
from sqlalchemy.exc import IntegrityError

from nosolear.persistence.db import create_engine_for, upgrade_to_head
from nosolear.persistence.repositories import ObservationRepository

OBS = SAMPLE_OBS[0]


def test_creates_data_dir_and_migrates(tmp_path: Path) -> None:
    eng = create_engine_for(f"sqlite:///{tmp_path}/nested/dir/x.sqlite")
    upgrade_to_head(eng)
    assert {
        "sessions",
        "attempts",
        "observations",
        "profile_entries",
        "profile_snapshots",
        "alembic_version",
    } <= set(inspect(eng).get_table_names())
    eng.dispose()


def test_upgrade_is_idempotent(db_engine: Engine) -> None:
    upgrade_to_head(db_engine)


def test_pragmas_set_on_every_connection(db_engine: Engine) -> None:
    for _ in range(2):
        with db_engine.connect() as conn:
            assert conn.execute(text("PRAGMA foreign_keys")).scalar_one() == 1
            assert conn.execute(text("PRAGMA journal_mode")).scalar_one() == "wal"


def test_foreign_keys_enforced(db_engine: Engine) -> None:
    with pytest.raises(IntegrityError):
        ObservationRepository(db_engine).add_many([replace(OBS, attempt_id="missing")])


def test_check_constraints(db_engine: Engine) -> None:
    with pytest.raises(IntegrityError), db_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO sessions (id, kind, protocol_version, started_at) "
                "VALUES ('s', 'bogus', 1, '2026-11-12T00:00:00+00:00')"
            )
        )
    with pytest.raises(IntegrityError):
        ObservationRepository(db_engine).add_many([replace(OBS, weight=0.0)])

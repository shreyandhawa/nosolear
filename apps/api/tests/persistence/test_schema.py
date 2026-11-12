"""Schema guards: models vs migrations drift, and DB-level enum CHECK constraints."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import IntegrityError

from nosolear.domain.observations import Context, Outcome
from nosolear.domain.status import Status
from nosolear.domain.taxonomy import Detector
from nosolear.persistence.db import create_engine_for, upgrade_to_head
from nosolear.persistence.models import metadata

STEP_KINDS = [
    "speak",
    "read_aloud",
    "word_list",
    "quick_answer",
    "articulate",
    "retell",
    "drill",
    "shadow",
]
TS = "2026-11-12T00:00:00.000000+00:00"


def test_models_match_migrations(db_engine: Engine) -> None:
    """Fails if `models.py` and the migrations disagree on tables, columns, types or indexes.

    Alembic does not compare CHECK constraints, so those are covered by the tests below.
    """
    with db_engine.connect() as conn:
        context = MigrationContext.configure(conn, opts={"compare_type": True})
        assert compare_metadata(context, metadata) == []


@pytest.fixture
def conn(db_engine: Engine) -> Iterator[Connection]:
    with db_engine.connect() as connection:
        connection.execute(
            text(
                "INSERT INTO sessions (id, kind, protocol_version, started_at) "
                f"VALUES ('s', 'daily', 1, '{TS}')"
            )
        )
        yield connection
        connection.rollback()


def _attempt(conn: Connection, step: str | int) -> None:
    conn.execute(
        text(
            "INSERT INTO attempts (id, session_id, step, scripted, created_at) "
            f"VALUES ('a', 's', :step, 1, '{TS}')"
        ),
        {"step": step},
    )


def _observation(conn: Connection, **overrides: str) -> None:
    values = {"outcome": "miss", "detector": "coach", "context": "scripted"} | overrides
    conn.execute(
        text(
            "INSERT INTO observations (error_key, outcome, weight, detector, context, "
            "observed_at, evidence_json, taxonomy_version, created_at) "
            "VALUES ('k', :outcome, 1.0, :detector, :context, "
            f"'{TS}', '{{}}', 1, '{TS}')"
        ),
        values,
    )


def _entry(conn: Connection, status: str) -> None:
    conn.execute(
        text(
            "INSERT INTO profile_entries (error_key, a, b, updated_at, p_hat, ci_low, ci_high, "
            "n_eff, status, last_seen_at, priority, as_of, algo_version, taxonomy_version) "
            f"VALUES ('k', 1, 3, '{TS}', 0.2, 0.1, 0.3, 1, :status, '{TS}', 0.2, '{TS}', 1, 1)"
        ),
        {"status": status},
    )


@pytest.mark.parametrize("step", STEP_KINDS)
def test_attempt_step_accepts_every_spec_kind(conn: Connection, step: str) -> None:
    _attempt(conn, step)


@pytest.mark.parametrize("step", ["bogus", "Speak", "1", ""])
def test_attempt_step_rejects_anything_else(conn: Connection, step: str) -> None:
    with pytest.raises(IntegrityError):
        _attempt(conn, step)


def test_attempt_step_is_text(conn: Connection) -> None:
    _attempt(conn, "speak")
    assert conn.execute(text("SELECT typeof(step) FROM attempts")).scalar_one() == "text"


@pytest.mark.parametrize(
    "column, enum", [("outcome", Outcome), ("detector", Detector), ("context", Context)]
)
def test_observation_enums_accept_members_and_reject_others(
    conn: Connection, column: str, enum: type[Outcome | Detector | Context]
) -> None:
    for member in enum:
        _observation(conn, **{column: member.value})
    with pytest.raises(IntegrityError):
        _observation(conn, **{column: "bogus"})
    with pytest.raises(IntegrityError):
        _observation(conn, **{column: next(iter(enum)).value.upper()})


def test_profile_status_accepts_members_and_rejects_others(conn: Connection) -> None:
    for status in Status:
        conn.execute(text("DELETE FROM profile_entries"))
        _entry(conn, status.value)
    conn.execute(text("DELETE FROM profile_entries"))
    with pytest.raises(IntegrityError):
        _entry(conn, "bogus")


def test_migration_0002_preserves_existing_rows(tmp_path: Path) -> None:
    engine = create_engine_for(f"sqlite:///{tmp_path / 'm.sqlite'}")
    upgrade_to_head(engine, revision="0001")
    with engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO sessions (id, kind, protocol_version, started_at) "
                f"VALUES ('s', 'daily', 1, '{TS}')"
            )
        )
        _observation(c)
        _entry(c, "active")
    upgrade_to_head(engine)
    with engine.connect() as c:
        assert c.execute(text("SELECT COUNT(*) FROM observations")).scalar_one() == 1
        assert c.execute(text("SELECT status FROM profile_entries")).scalar_one() == "active"
        assert c.execute(text("SELECT COUNT(*) FROM sessions")).scalar_one() == 1
    engine.dispose()


def test_migration_0003_backfills_nepali(tmp_path: Path) -> None:
    engine = create_engine_for(f"sqlite:///{tmp_path / 'm.sqlite'}")
    upgrade_to_head(engine, revision="0002")
    with engine.begin() as c:
        _entry(c, "active")
        c.execute(
            text(
                "INSERT INTO profile_snapshots (id, reason, taken_at, as_of, algo_version, "
                "taxonomy_version, entries_json) "
                f"VALUES ('x', 'rebuild', '{TS}', '{TS}', 1, 1, '[]')"
            )
        )
    upgrade_to_head(engine)
    with engine.connect() as c:
        assert c.execute(text("SELECT pack_id FROM profile_entries")).scalar_one() == "nepali"
        assert c.execute(text("SELECT pack_id FROM profile_snapshots")).scalar_one() == "nepali"
    engine.dispose()

"""Schema guards: models vs migrations drift, and DB-level enum CHECK constraints."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import Connection, Engine, inspect, text
from sqlalchemy.exc import IntegrityError

from nosolear.domain.observations import Context, Outcome
from nosolear.domain.status import Status
from nosolear.domain.taxonomy import Detector
from nosolear.persistence.db import MIGRATIONS_DIR, create_engine_for, upgrade_to_head
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


def _attempt_row(conn: Connection, attempt_id: str = "a") -> None:
    conn.execute(
        text(
            "INSERT INTO attempts (id, session_id, step, scripted, created_at) "
            f"VALUES (:id, 's', 'speak', 1, '{TS}')"
        ),
        {"id": attempt_id},
    )


def _recording(conn: Connection, **overrides: str | int) -> None:
    values: dict[str, str | int] = {
        "id": "r1",
        "attempt_id": "a",
        "path": "recordings/x.wav",
        "sample_rate": 16000,
    } | overrides
    conn.execute(
        text(
            "INSERT INTO recordings (id, attempt_id, path, duration_ms, sample_rate, sha256, "
            f"created_at) VALUES (:id, :attempt_id, :path, 1000, :sample_rate, 'h', '{TS}')"
        ),
        values,
    )


def test_recordings_unique_per_attempt_and_path_shape(conn: Connection) -> None:
    _attempt_row(conn)
    _recording(conn)
    with pytest.raises(IntegrityError):
        _recording(conn, id="r2", path="recordings/y.wav")
    _attempt_row(conn, "b")
    with pytest.raises(IntegrityError):
        _recording(conn, id="r3", attempt_id="b", path="../x.wav")
    with pytest.raises(IntegrityError):
        _recording(conn, id="r4", attempt_id="b", path="recordings/z.wav", sample_rate=48000)
    with pytest.raises(IntegrityError):
        _recording(conn, id="r5", attempt_id="b")  # same path as r1


def _job(conn: Connection, **overrides: str | float | None) -> None:
    values: dict[str, str | float | None] = {
        "id": "j1",
        "kind": "analyze",
        "attempt_id": None,
        "status": "queued",
        "progress": 0.0,
    } | overrides
    conn.execute(
        text(
            "INSERT INTO jobs (id, kind, attempt_id, status, progress, steps_json, tries, "
            f"created_at, updated_at) VALUES (:id, :kind, :attempt_id, :status, :progress, "
            f"'[]', 0, '{TS}', '{TS}')"
        ),
        values,
    )


def test_jobs_checks(conn: Connection) -> None:
    _job(conn, id="ok", kind="rescore", attempt_id=None)
    for bad in ({"kind": "bogus"}, {"status": "bogus"}, {"progress": 1.5}):
        with pytest.raises(IntegrityError):
            _job(conn, **bad)
    with pytest.raises(IntegrityError):
        conn.execute(
            text(
                "INSERT INTO jobs (id, kind, status, progress, steps_json, tries, created_at, "
                f"updated_at) VALUES ('t', 'analyze', 'queued', 0, '[]', -1, '{TS}', '{TS}')"
            )
        )


def _ledger(conn: Connection, **overrides: str | int | None) -> None:
    values: dict[str, str | int | None] = {
        "provider": "azure",
        "unit": "audio_seconds",
        "state": "reserved",
        "actual": None,
        "job_id": None,
    } | overrides
    conn.execute(
        text(
            "INSERT INTO usage_ledger (provider, unit, state, estimate, actual, period, job_id, "
            f"created_at) VALUES (:provider, :unit, :state, 5, :actual, '2026-11', :job_id, "
            f"'{TS}')"
        ),
        values,
    )


def test_ledger_checks(conn: Connection) -> None:
    _ledger(conn)  # job_id NULL accepted
    _ledger(conn, state="recorded", actual=4)
    _ledger(conn, state="released")
    bad_rows: list[dict[str, str | int | None]] = [
        {"provider": "bogus"},
        {"unit": "bogus"},
        {"state": "bogus"},
        {"state": "recorded", "actual": None},
        {"state": "reserved", "actual": 3},
    ]
    for bad in bad_rows:
        with pytest.raises(IntegrityError):
            _ledger(conn, **bad)
    with pytest.raises(IntegrityError):
        _ledger(conn, job_id="missing")  # foreign key


def _analysis(conn: Connection, **overrides: str | None) -> None:
    values: dict[str, str | None] = {
        "attempt_id": "a",
        "tts_hash": None,
        "calibration_run_id": None,
        "kind": "pronunciation",
    } | overrides
    conn.execute(
        text(
            "INSERT INTO analyses (attempt_id, tts_hash, calibration_run_id, kind, provider, "
            "provider_version, adapter, adapter_version, raw_json, created_at) VALUES "
            f"(:attempt_id, :tts_hash, :calibration_run_id, :kind, 'azure', 'v', 'ad', 1, '{{}}', "
            f"'{TS}')"
        ),
        values,
    )


def test_analyses_exactly_one_key_shape(conn: Connection) -> None:
    _attempt_row(conn)
    _analysis(conn)
    with pytest.raises(IntegrityError):
        _analysis(conn, tts_hash="h", calibration_run_id="c", kind="transcript")  # both
    with pytest.raises(IntegrityError):
        _analysis(conn, attempt_id=None, kind="transcript")  # neither
    with pytest.raises(IntegrityError):
        _analysis(conn, attempt_id=None, tts_hash="h", kind="transcript")  # no run
    with pytest.raises(IntegrityError):
        _analysis(conn, tts_hash="h", kind="transcript")  # attempt and hash, no run
    with pytest.raises(IntegrityError):
        _analysis(conn)  # duplicate (attempt_id, kind)
    with pytest.raises(IntegrityError):
        _analysis(conn, kind="bogus")
    _analysis(conn, attempt_id=None, tts_hash="h", calibration_run_id="c1")
    _analysis(conn, attempt_id=None, tts_hash="h", calibration_run_id="c2")
    with pytest.raises(IntegrityError):
        _analysis(conn, attempt_id=None, tts_hash="h", calibration_run_id="c1")


def test_migration_downgrade_then_upgrade(tmp_path: Path) -> None:
    engine = create_engine_for(f"sqlite:///{tmp_path / 'm.sqlite'}")
    upgrade_to_head(engine)
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    new_tables = {"recordings", "jobs", "usage_ledger", "analyses"}
    with engine.begin() as c:
        config.attributes["connection"] = c
        command.downgrade(config, "0003")
    assert not new_tables & set(inspect(engine).get_table_names())
    upgrade_to_head(engine)
    assert new_tables <= set(inspect(engine).get_table_names())
    engine.dispose()

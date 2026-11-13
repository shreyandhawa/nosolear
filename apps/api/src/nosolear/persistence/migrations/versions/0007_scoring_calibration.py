"""Scoring configs, calibration, content items, skill scores and extractions

Adds the `v0` scoring config row, tags every existing observation with it, and records one
extraction marker per (attempt, detector) so the profile reads the newest config per attempt.

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-13
"""

import json
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from functools import partial

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# A frozen copy of `domain.scoring.V0_RULES_JSON`. A migration must not change when the domain does.
V0_RULES_JSON: dict[str, object] = {
    "schema": 1,
    "thresholds": {
        "nbest_margin": 30.0,
        "low_accuracy": 40.0,
        "slow_start_ms": 3000,
        "long_pause_ms": 2000,
    },
    "family_rules": [
        {"detector": "asr_metrics", "family": "fluency", "enabled": True, "provisional": False},
        {"detector": "azure_pa", "family": "prosody", "enabled": True, "provisional": True},
        {"detector": "azure_pa", "family": "sound.low", "enabled": True, "provisional": True},
        {"detector": "azure_pa", "family": "sound.sub", "enabled": True, "provisional": True},
        {"detector": "coach", "family": "clarity", "enabled": True, "provisional": False},
        {"detector": "coach", "family": "grammar", "enabled": True, "provisional": False},
        {"detector": "coach", "family": "structure", "enabled": True, "provisional": False},
        {"detector": "phone_probe", "family": "sound.del", "enabled": False, "provisional": True},
        {"detector": "phone_probe", "family": "sound.ins", "enabled": False, "provisional": True},
        {"detector": "phone_probe", "family": "sound.sub", "enabled": False, "provisional": True},
    ],
    "key_rules": [],
}

DETECTORS = ("azure_pa", "phone_probe", "asr_metrics", "coach")
SESSION_KINDS_0006 = ("baseline", "daily", "retest", "conversation")
SESSION_KINDS = (*SESSION_KINDS_0006, "calibration")
STEPS_0006 = (
    "speak",
    "read_aloud",
    "word_list",
    "quick_answer",
    "articulate",
    "retell",
    "drill",
    "shadow",
)
STEPS = (*STEPS_0006, "calibration")
JOB_KINDS_0006 = ("analyze", "rescore")
JOB_KINDS = (*JOB_KINDS_0006, "calibrate")
CONTENT_KINDS = (
    "prompt",
    "passage_sentence",
    "minimal_pair",
    "drill_sentence",
    "starter",
    "quick_question",
    "calibration_word",
)


def _in(column: str, values: Sequence[str]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _rebuild(
    table: str, create: Callable[[str], str], columns: str, after: Sequence[str] = ()
) -> None:
    """Rebuild a table that other tables reference, keeping its rows.

    The SQLite recipe: create the new table under a temporary name, copy, drop the old one,
    rename. Children keep naming `table`, so they point at the rebuilt table afterwards. This runs
    with foreign keys off (see `foreign_keys_off`), so the drop is not checked. `after` runs once
    the new table has its name.
    """
    op.execute(create(f"{table}_new"))
    op.execute(f"INSERT INTO {table}_new ({columns}) SELECT {columns} FROM {table}")
    op.execute(f"DROP TABLE {table}")
    op.execute(f"ALTER TABLE {table}_new RENAME TO {table}")
    for statement in after:
        op.execute(statement)


def _sessions_sql(name: str, kinds: Sequence[str]) -> str:
    return (
        f"CREATE TABLE {name} ("
        "id VARCHAR NOT NULL, kind VARCHAR NOT NULL, protocol_version INTEGER NOT NULL, "
        "started_at VARCHAR NOT NULL, completed_at VARCHAR, PRIMARY KEY (id), "
        f"CONSTRAINT ck_sessions_kind CHECK ({_in('kind', kinds)}))"
    )


def _attempts_sql(name: str, steps: Sequence[str], content_fk: bool) -> str:
    content_column = ", content_item_id VARCHAR" if content_fk else ""
    content_key = (
        ", FOREIGN KEY(content_item_id) REFERENCES content_items (id)" if content_fk else ""
    )
    return (
        f"CREATE TABLE {name} ("
        "id VARCHAR NOT NULL, session_id VARCHAR NOT NULL, step VARCHAR NOT NULL, "
        "reference_text TEXT, scripted BOOLEAN NOT NULL, created_at VARCHAR NOT NULL"
        f"{content_column}, PRIMARY KEY (id), "
        f"FOREIGN KEY(session_id) REFERENCES sessions (id){content_key}, "
        f"CONSTRAINT ck_attempts_step CHECK ({_in('step', steps)}))"
    )


def _jobs_sql(name: str, kinds: Sequence[str]) -> str:
    return (
        f"CREATE TABLE {name} ("
        "id VARCHAR NOT NULL, kind VARCHAR NOT NULL, attempt_id VARCHAR, "
        "status VARCHAR NOT NULL, step VARCHAR, progress FLOAT NOT NULL, "
        "steps_json TEXT NOT NULL, tries INTEGER NOT NULL, created_at VARCHAR NOT NULL, "
        "updated_at VARCHAR NOT NULL, PRIMARY KEY (id), "
        "FOREIGN KEY(attempt_id) REFERENCES attempts (id), "
        f"CONSTRAINT ck_jobs_kind CHECK ({_in('kind', kinds)}), "
        "CONSTRAINT ck_jobs_status CHECK (status IN ('queued', 'running', 'done', 'failed')), "
        "CONSTRAINT ck_jobs_progress CHECK (progress BETWEEN 0 AND 1), "
        "CONSTRAINT ck_jobs_tries CHECK (tries >= 0))"
    )


JOBS_STATUS_INDEX = "CREATE INDEX ix_jobs_status_created ON jobs (status, created_at)"
SESSIONS_COLUMNS = "id, kind, protocol_version, started_at, completed_at"
ATTEMPTS_COLUMNS = "id, session_id, step, reference_text, scripted, created_at"
JOBS_COLUMNS = (
    "id, kind, attempt_id, status, step, progress, steps_json, tries, created_at, updated_at"
)


def upgrade() -> None:
    op.create_table(
        "content_items",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("target_keys", sa.Text(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("retired_at", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(_in("kind", CONTENT_KINDS), name="ck_content_items_kind"),
        sa.CheckConstraint("source IN ('seed', 'coach')", name="ck_content_items_source"),
    )
    # calibration_runs and scoring_configs reference each other; SQLite checks that on writes,
    # not on CREATE, so either order works.
    op.create_table(
        "calibration_runs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("scoring_config_id", sa.String(), nullable=True),
        sa.Column("started_at", sa.String(), nullable=False),
        sa.Column("completed_at", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"]),
        sa.ForeignKeyConstraint(
            ["scoring_config_id"],
            ["scoring_configs.id"],
            name="fk_calibration_runs_scoring_config_id",
        ),
        sa.CheckConstraint(
            "status IN ('running', 'done', 'skipped')", name="ck_calibration_runs_status"
        ),
    )
    op.create_table(
        "scoring_configs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("calibration_run_id", sa.String(), nullable=True),
        sa.Column("rules_json", sa.Text(), nullable=False),
        sa.Column("capabilities_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["calibration_run_id"], ["calibration_runs.id"]),
        sa.CheckConstraint("kind IN ('v0', 'calibrated')", name="ck_scoring_configs_kind"),
        sa.CheckConstraint(
            "(kind = 'v0') = (calibration_run_id IS NULL)", name="ck_scoring_configs_run"
        ),
    )
    op.create_table(
        "calibration_trials",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("error_key", sa.String(), nullable=False),
        sa.Column("detector", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("attempt_id", sa.String(), nullable=True),
        sa.Column("tts_hash", sa.String(), nullable=True),
        sa.Column("flagged", sa.Boolean(), nullable=True),
        sa.Column("evidence_json", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["calibration_runs.id"]),
        sa.ForeignKeyConstraint(["attempt_id"], ["attempts.id"]),
        sa.ForeignKeyConstraint(["tts_hash"], ["tts_cache.hash"]),
        sa.CheckConstraint("kind IN ('error', 'control')", name="ck_calibration_trials_kind"),
        sa.CheckConstraint(_in("detector", DETECTORS), name="ck_calibration_trials_detector"),
        sa.CheckConstraint(
            "(attempt_id IS NULL) <> (tts_hash IS NULL)", name="ck_calibration_trials_subject"
        ),
        sa.CheckConstraint(
            "kind = 'control' OR attempt_id IS NOT NULL",
            name="ck_calibration_trials_error_attempt",
        ),
    )
    op.create_index(
        "uq_calibration_trials_attempt",
        "calibration_trials",
        ["run_id", "error_key", "detector", "attempt_id"],
        unique=True,
        sqlite_where=sa.text("attempt_id IS NOT NULL"),
    )
    op.create_index(
        "uq_calibration_trials_tts",
        "calibration_trials",
        ["run_id", "error_key", "detector", "tts_hash"],
        unique=True,
        sqlite_where=sa.text("tts_hash IS NOT NULL"),
    )
    op.create_table(
        "skill_scores",
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("skill", sa.String(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("components_json", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("session_id", "skill"),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"]),
        sa.CheckConstraint(
            _in("skill", ("sounds", "on_the_spot", "articulate")), name="ck_skill_scores_skill"
        ),
        sa.CheckConstraint("score BETWEEN 0 AND 100", name="ck_skill_scores_score"),
    )
    op.create_table(
        "extractions",
        sa.Column("attempt_id", sa.String(), nullable=False),
        sa.Column("scoring_config_id", sa.String(), nullable=False),
        sa.Column("detector", sa.String(), nullable=False),
        sa.Column("observation_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("attempt_id", "scoring_config_id", "detector"),
        sa.ForeignKeyConstraint(["attempt_id"], ["attempts.id"]),
        sa.ForeignKeyConstraint(["scoring_config_id"], ["scoring_configs.id"]),
        sa.CheckConstraint(_in("detector", DETECTORS), name="ck_extractions_detector"),
        sa.CheckConstraint("observation_count >= 0", name="ck_extractions_count"),
    )

    op.get_bind().execute(
        sa.text(
            "INSERT INTO scoring_configs (id, kind, calibration_run_id, rules_json, "
            "capabilities_json, created_at) VALUES ('v0', 'v0', NULL, :rules, '{}', :now)"
        ),
        {
            "rules": _canonical(V0_RULES_JSON),
            "now": datetime.now(UTC).isoformat(timespec="microseconds"),
        },
    )

    # Parents with child rows: rebuilt by hand, see _rebuild.
    _rebuild("sessions", partial(_sessions_sql, kinds=SESSION_KINDS), SESSIONS_COLUMNS)
    _rebuild(
        "attempts",
        partial(_attempts_sql, steps=STEPS, content_fk=True),
        ATTEMPTS_COLUMNS,
    )
    _rebuild("jobs", partial(_jobs_sql, kinds=JOB_KINDS), JOBS_COLUMNS, after=[JOBS_STATUS_INDEX])

    # No child rows reference these, so alembic's batch mode is safe here.
    with op.batch_alter_table("observations", recreate="always") as batch:
        batch.add_column(sa.Column("scoring_config_id", sa.String(), nullable=True))
        batch.add_column(sa.Column("provisional", sa.Boolean(), nullable=True))
        batch.create_foreign_key(
            "fk_observations_scoring_config_id", "scoring_configs", ["scoring_config_id"], ["id"]
        )
    op.execute(
        "UPDATE observations SET scoring_config_id = 'v0', "
        "provisional = (error_key LIKE 'sound.%' OR error_key LIKE 'prosody.%')"
    )
    with op.batch_alter_table("observations", recreate="always") as batch:
        batch.alter_column("scoring_config_id", existing_type=sa.String(), nullable=False)
        batch.alter_column("provisional", existing_type=sa.Boolean(), nullable=False)

    with op.batch_alter_table("profile_entries", recreate="always") as batch:
        batch.add_column(
            sa.Column("provisional", sa.Boolean(), nullable=False, server_default=sa.false())
        )

    with op.batch_alter_table("analyses", recreate="always") as batch:
        batch.create_foreign_key("fk_analyses_tts_hash", "tts_cache", ["tts_hash"], ["hash"])
        batch.create_foreign_key(
            "fk_analyses_calibration_run_id", "calibration_runs", ["calibration_run_id"], ["id"]
        )

    op.execute(
        "INSERT INTO extractions (attempt_id, scoring_config_id, detector, observation_count, "
        "created_at) SELECT attempt_id, 'v0', detector, COUNT(*), MIN(created_at) "
        "FROM observations WHERE attempt_id IS NOT NULL GROUP BY attempt_id, detector"
    )


def downgrade() -> None:
    with op.batch_alter_table("analyses", recreate="always") as batch:
        batch.drop_constraint("fk_analyses_calibration_run_id", type_="foreignkey")
        batch.drop_constraint("fk_analyses_tts_hash", type_="foreignkey")

    with op.batch_alter_table("profile_entries", recreate="always") as batch:
        batch.drop_column("provisional")

    with op.batch_alter_table("observations", recreate="always") as batch:
        batch.drop_constraint("fk_observations_scoring_config_id", type_="foreignkey")
        batch.drop_column("provisional")
        batch.drop_column("scoring_config_id")

    _rebuild(
        "jobs",
        partial(_jobs_sql, kinds=JOB_KINDS_0006),
        JOBS_COLUMNS,
        after=[JOBS_STATUS_INDEX],
    )
    _rebuild(
        "attempts",
        partial(_attempts_sql, steps=STEPS_0006, content_fk=False),
        ATTEMPTS_COLUMNS,
    )
    _rebuild("sessions", partial(_sessions_sql, kinds=SESSION_KINDS_0006), SESSIONS_COLUMNS)

    op.drop_table("extractions")
    op.drop_table("skill_scores")
    op.drop_table("calibration_trials")
    op.drop_table("scoring_configs")
    op.drop_table("calibration_runs")
    op.drop_table("content_items")

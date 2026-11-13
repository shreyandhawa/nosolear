"""recordings, jobs, usage ledger and analyses

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "recordings",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("attempt_id", sa.String(), nullable=False),
        sa.Column("path", sa.String(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("sample_rate", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["attempt_id"], ["attempts.id"]),
        sa.UniqueConstraint("attempt_id"),
        sa.UniqueConstraint("path"),
        sa.CheckConstraint("path GLOB 'recordings/*.wav'", name="ck_recordings_path"),
        sa.CheckConstraint("duration_ms >= 0", name="ck_recordings_duration"),
        sa.CheckConstraint("sample_rate = 16000", name="ck_recordings_sample_rate"),
    )
    op.create_table(
        "jobs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("attempt_id", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("step", sa.String(), nullable=True),
        sa.Column("progress", sa.Float(), nullable=False),
        sa.Column("steps_json", sa.Text(), nullable=False),
        sa.Column("tries", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["attempt_id"], ["attempts.id"]),
        sa.CheckConstraint("kind IN ('analyze', 'rescore')", name="ck_jobs_kind"),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'done', 'failed')", name="ck_jobs_status"
        ),
        sa.CheckConstraint("progress BETWEEN 0 AND 1", name="ck_jobs_progress"),
        sa.CheckConstraint("tries >= 0", name="ck_jobs_tries"),
    )
    op.create_index("ix_jobs_status_created", "jobs", ["status", "created_at"])
    op.create_table(
        "usage_ledger",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("unit", sa.String(), nullable=False),
        sa.Column("state", sa.String(), nullable=False),
        sa.Column("estimate", sa.Integer(), nullable=False),
        sa.Column("actual", sa.Integer(), nullable=True),
        sa.Column("period", sa.String(), nullable=False),
        sa.Column("job_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("settled_at", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"]),
        sa.CheckConstraint("provider IN ('azure', 'anthropic')", name="ck_usage_ledger_provider"),
        sa.CheckConstraint(
            "unit IN ('audio_seconds', 'tts_chars', 'tokens')", name="ck_usage_ledger_unit"
        ),
        sa.CheckConstraint(
            "state IN ('reserved', 'recorded', 'released')", name="ck_usage_ledger_state"
        ),
        sa.CheckConstraint("estimate >= 0", name="ck_usage_ledger_estimate"),
        sa.CheckConstraint(
            "(state = 'recorded') = (actual IS NOT NULL)", name="ck_usage_ledger_actual"
        ),
    )
    op.create_index("ix_ledger_totals", "usage_ledger", ["provider", "unit", "period", "state"])
    op.create_table(
        "analyses",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("attempt_id", sa.String(), nullable=True),
        sa.Column("tts_hash", sa.String(), nullable=True),
        sa.Column("calibration_run_id", sa.String(), nullable=True),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("provider_version", sa.String(), nullable=False),
        sa.Column("adapter", sa.String(), nullable=False),
        sa.Column("adapter_version", sa.Integer(), nullable=False),
        sa.Column("raw_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["attempt_id"], ["attempts.id"]),
        sa.CheckConstraint(
            "kind IN ('pronunciation', 'transcript', 'phone_probe', 'coach')",
            name="ck_analyses_kind",
        ),
        sa.CheckConstraint(
            "(attempt_id IS NOT NULL AND tts_hash IS NULL AND calibration_run_id IS NULL) OR "
            "(attempt_id IS NULL AND tts_hash IS NOT NULL AND calibration_run_id IS NOT NULL)",
            name="ck_analyses_key_shape",
        ),
    )
    op.create_index(
        "uq_analyses_attempt_kind",
        "analyses",
        ["attempt_id", "kind"],
        unique=True,
        sqlite_where=sa.text("attempt_id IS NOT NULL"),
    )
    op.create_index(
        "uq_analyses_tts_kind_run",
        "analyses",
        ["tts_hash", "kind", "calibration_run_id"],
        unique=True,
        sqlite_where=sa.text("attempt_id IS NULL"),
    )


def downgrade() -> None:
    # Children first: usage_ledger references jobs.
    for table in ("analyses", "usage_ledger", "jobs", "recordings"):
        op.drop_table(table)

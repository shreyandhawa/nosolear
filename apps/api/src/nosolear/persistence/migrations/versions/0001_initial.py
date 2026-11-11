"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-11-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sessions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("protocol_version", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.String(), nullable=False),
        sa.Column("completed_at", sa.String(), nullable=True),
        sa.CheckConstraint(
            "kind IN ('baseline', 'daily', 'retest', 'conversation')", name="ck_sessions_kind"
        ),
    )
    op.create_table(
        "attempts",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("session_id", sa.String(), sa.ForeignKey("sessions.id"), nullable=False),
        sa.Column("step", sa.Integer(), nullable=False),
        sa.Column("reference_text", sa.Text(), nullable=True),
        sa.Column("scripted", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
    )
    op.create_table(
        "observations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("attempt_id", sa.String(), sa.ForeignKey("attempts.id"), nullable=True),
        sa.Column("error_key", sa.String(), nullable=False),
        sa.Column("outcome", sa.String(), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False),
        sa.Column("detector", sa.String(), nullable=False),
        sa.Column("context", sa.String(), nullable=False),
        sa.Column("observed_at", sa.String(), nullable=False),
        sa.Column("evidence_json", sa.Text(), nullable=False),
        sa.Column("taxonomy_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.CheckConstraint("weight > 0 AND weight <= 1", name="ck_observations_weight"),
    )
    op.create_table(
        "profile_entries",
        sa.Column("error_key", sa.String(), primary_key=True),
        sa.Column("a", sa.Float(), nullable=False),
        sa.Column("b", sa.Float(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
        sa.Column("p_hat", sa.Float(), nullable=False),
        sa.Column("ci_low", sa.Float(), nullable=False),
        sa.Column("ci_high", sa.Float(), nullable=False),
        sa.Column("n_eff", sa.Float(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("last_seen_at", sa.String(), nullable=False),
        sa.Column("priority", sa.Float(), nullable=False),
        sa.Column("as_of", sa.String(), nullable=False),
        sa.Column("algo_version", sa.Integer(), nullable=False),
        sa.Column("taxonomy_version", sa.Integer(), nullable=False),
    )
    op.create_table(
        "profile_snapshots",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("session_id", sa.String(), sa.ForeignKey("sessions.id"), nullable=True),
        sa.Column("reason", sa.String(), nullable=False),
        sa.Column("taken_at", sa.String(), nullable=False),
        sa.Column("as_of", sa.String(), nullable=False),
        sa.Column("algo_version", sa.Integer(), nullable=False),
        sa.Column("taxonomy_version", sa.Integer(), nullable=False),
        sa.Column("entries_json", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "reason IN ('rebuild', 'baseline', 'daily', 'retest')",
            name="ck_profile_snapshots_reason",
        ),
    )


def downgrade() -> None:
    for table in ("profile_snapshots", "profile_entries", "observations", "attempts", "sessions"):
        op.drop_table(table)

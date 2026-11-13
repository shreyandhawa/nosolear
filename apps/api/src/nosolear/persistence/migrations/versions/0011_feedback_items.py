"""feedback_items: one stored feedback item per session and skill

Each row says where its words came from (`source`: the coach or a template) and, for a template,
why the coach was not used (`fallback_reason`). The unique (session, skill) pair keeps one card per
skill; a later request replaces a template in place.

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "feedback_items",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("skill", sa.String(), nullable=False),
        sa.Column("error_key", sa.String(), nullable=False),
        sa.Column("observation_id", sa.Integer(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("model_text", sa.Text(), nullable=True),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("fallback_reason", sa.String(), nullable=True),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.CheckConstraint(
            "skill IN ('sounds', 'on_the_spot', 'articulate')", name="ck_feedback_items_skill"
        ),
        sa.CheckConstraint("source IN ('coach', 'template')", name="ck_feedback_items_source"),
        sa.CheckConstraint(
            "fallback_reason IN ('cap_exceeded', 'provider_unavailable', "
            "'capability_missing', 'invalid_output')",
            name="ck_feedback_items_fallback_reason",
        ),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"]),
        sa.ForeignKeyConstraint(["observation_id"], ["observations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "skill", name="uq_feedback_items_session_skill"),
    )


def downgrade() -> None:
    op.drop_table("feedback_items")

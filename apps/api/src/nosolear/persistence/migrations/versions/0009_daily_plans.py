"""daily_plans: one stored plan per local date

Each row freezes the day's focus, prompt and drills (`drills_json` keeps the prompt text, so the
plan survives a later retirement of its content item) and the seed it was drawn with.

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "daily_plans",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("for_date", sa.String(), nullable=False),
        sa.Column("focus_json", sa.Text(), nullable=False),
        sa.Column("prompt_item_id", sa.String(), nullable=True),
        sa.Column("drills_json", sa.Text(), nullable=False),
        sa.Column("seed", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["prompt_item_id"], ["content_items.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("for_date", name="uq_daily_plans_for_date"),
    )


def downgrade() -> None:
    op.drop_table("daily_plans")

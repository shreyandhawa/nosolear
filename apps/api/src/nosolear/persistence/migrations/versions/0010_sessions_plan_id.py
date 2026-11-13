"""sessions.plan_id: one daily session per plan

A daily session names the plan it runs. The unique index keeps it to one session per plan, so a
repeated start returns the session that exists. Baseline sessions keep NULL.

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("sessions") as batch:
        batch.add_column(sa.Column("plan_id", sa.String(), nullable=True))
        batch.create_foreign_key("fk_sessions_plan_id", "daily_plans", ["plan_id"], ["id"])
    op.create_index("ux_sessions_plan_id", "sessions", ["plan_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ux_sessions_plan_id", table_name="sessions")
    with op.batch_alter_table("sessions") as batch:
        batch.drop_constraint("fk_sessions_plan_id", type_="foreignkey")
        batch.drop_column("plan_id")

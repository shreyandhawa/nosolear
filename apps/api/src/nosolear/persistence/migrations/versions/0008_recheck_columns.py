"""profile_entries carry the re-check schedule of mastered keys

Adds two nullable columns: `next_recheck_at` (when the key is next re-checked) and `recheck_stage`
(its rung on the ladder). Rows without a schedule, which is every non-mastered key, keep NULL.

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("profile_entries") as batch:
        batch.add_column(sa.Column("next_recheck_at", sa.String(), nullable=True))
        batch.add_column(sa.Column("recheck_stage", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("profile_entries") as batch:
        batch.drop_column("recheck_stage")
        batch.drop_column("next_recheck_at")

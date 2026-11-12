"""profile_entries and profile_snapshots record the language pack their priors came from

Phase 0a rows were built with the hypothesis priors that now live in the `nepali` pack, so
existing rows are backfilled with that id. The models carry no server default: every write names
its pack.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for table in ("profile_entries", "profile_snapshots"):
        op.add_column(
            table, sa.Column("pack_id", sa.String(), nullable=False, server_default="nepali")
        )


def downgrade() -> None:
    for table in ("profile_snapshots", "profile_entries"):
        with op.batch_alter_table(table) as batch:
            batch.drop_column("pack_id")

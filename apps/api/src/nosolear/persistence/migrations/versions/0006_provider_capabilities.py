"""provider_capabilities: what each live probe measured, with the region and locale it used

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "provider_capabilities",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("adapter", sa.String(), nullable=False),
        sa.Column("adapter_version", sa.Integer(), nullable=False),
        sa.Column("provider_version", sa.String(), nullable=False),
        sa.Column("region", sa.String(), nullable=True),
        sa.Column("locale", sa.String(), nullable=True),
        sa.Column("capabilities_json", sa.Text(), nullable=False),
        sa.Column("probed_at", sa.String(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("provider_capabilities")

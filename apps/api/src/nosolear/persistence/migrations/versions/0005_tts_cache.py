"""tts_cache: one row per synthesized clip, keyed by the SSML hash

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tts_cache",
        sa.Column("hash", sa.String(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("voice", sa.String(), nullable=False),
        sa.Column("rate", sa.Integer(), nullable=False),
        sa.Column("path", sa.String(), nullable=False),
        sa.Column("word_timings_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("hash"),
        sa.CheckConstraint("path = 'tts/' || hash || '.wav'", name="ck_tts_cache_path"),
    )


def downgrade() -> None:
    op.drop_table("tts_cache")

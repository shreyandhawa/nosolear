"""attempts.step becomes the spec's step-kind text; CHECK constraints on enum-like columns

SQLite cannot change a column type or add a constraint in place, so each table is rebuilt in
batch mode. Nothing writes `attempts` before Phase 0c, so no integer `step` values exist to
convert.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STEPS = (
    "'speak', 'read_aloud', 'word_list', 'quick_answer', 'articulate', 'retell', 'drill', 'shadow'"
)


def upgrade() -> None:
    # Rebuilding a parent table (attempts) must not trip foreign keys mid-migration; the pragma
    # works inside a transaction and checks them at commit instead.
    op.execute("PRAGMA defer_foreign_keys=ON")
    with op.batch_alter_table("attempts") as batch:
        batch.alter_column("step", existing_type=sa.Integer(), type_=sa.String(), nullable=False)
        batch.create_check_constraint("ck_attempts_step", f"step IN ({STEPS})")
    with op.batch_alter_table("observations") as batch:
        batch.create_check_constraint("ck_observations_outcome", "outcome IN ('miss', 'ok')")
        batch.create_check_constraint(
            "ck_observations_detector",
            "detector IN ('azure_pa', 'phone_probe', 'asr_metrics', 'coach')",
        )
        batch.create_check_constraint(
            "ck_observations_context", "context IN ('scripted', 'unscripted')"
        )
    with op.batch_alter_table("profile_entries") as batch:
        batch.create_check_constraint(
            "ck_profile_entries_status",
            "status IN ('unknown', 'active', 'improving', 'watching', 'mastered')",
        )


def downgrade() -> None:
    op.execute("PRAGMA defer_foreign_keys=ON")
    with op.batch_alter_table("profile_entries") as batch:
        batch.drop_constraint("ck_profile_entries_status", type_="check")
    with op.batch_alter_table("observations") as batch:
        batch.drop_constraint("ck_observations_context", type_="check")
        batch.drop_constraint("ck_observations_detector", type_="check")
        batch.drop_constraint("ck_observations_outcome", type_="check")
    with op.batch_alter_table("attempts") as batch:
        batch.drop_constraint("ck_attempts_step", type_="check")
        batch.alter_column("step", existing_type=sa.String(), type_=sa.Integer(), nullable=False)

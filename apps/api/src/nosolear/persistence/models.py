"""SQLite schema (ARCHITECTURE.md section 7) as SQLAlchemy Core tables."""

from collections.abc import Iterable
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Dialect,
    Float,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
)
from sqlalchemy import Column as C
from sqlalchemy.types import TypeDecorator

from nosolear.domain.observations import Context, Outcome
from nosolear.domain.status import Status
from nosolear.domain.taxonomy import Detector


def format_utc(value: datetime) -> str:
    """The one stored text form of a datetime: UTC, fixed width, microseconds (`...+00:00`).

    Fixed width keeps text ordering chronological. Used by `UTCDateTime` and by JSON snapshots.
    """
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(UTC).isoformat(timespec="microseconds")


class UTCDateTime(TypeDecorator[datetime]):
    """Aware datetimes stored as ISO-8601 text in UTC (`...+00:00`); naive input is an error."""

    impl = String
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> str | None:
        if value is None:
            return None
        return format_utc(value)

    def process_result_value(self, value: str | None, dialect: Dialect) -> datetime | None:
        return None if value is None else datetime.fromisoformat(value).astimezone(UTC)


metadata = MetaData()

# ARCHITECTURE.md section 7 (`attempts.step`).
ATTEMPT_STEPS = (
    "speak",
    "read_aloud",
    "word_list",
    "quick_answer",
    "articulate",
    "retell",
    "drill",
    "shadow",
)


def _in_list(column: str, values: Iterable[str]) -> str:
    return f"{column} IN ({', '.join(repr(str(v)) for v in values)})"


sessions = Table(
    "sessions",
    metadata,
    C("id", String, primary_key=True),
    C("kind", String, nullable=False),
    C("protocol_version", Integer, nullable=False),
    C("started_at", UTCDateTime, nullable=False),
    C("completed_at", UTCDateTime, nullable=True),
    CheckConstraint(
        "kind IN ('baseline', 'daily', 'retest', 'conversation')", name="ck_sessions_kind"
    ),
)

attempts = Table(
    "attempts",
    metadata,
    C("id", String, primary_key=True),
    C("session_id", String, ForeignKey("sessions.id"), nullable=False),
    C("step", String, nullable=False),
    C("reference_text", Text, nullable=True),
    C("scripted", Boolean, nullable=False),
    C("created_at", UTCDateTime, nullable=False),
    CheckConstraint(_in_list("step", ATTEMPT_STEPS), name="ck_attempts_step"),
)

observations = Table(
    "observations",
    metadata,
    C("id", Integer, primary_key=True, autoincrement=True),
    C("attempt_id", String, ForeignKey("attempts.id"), nullable=True),
    C("error_key", String, nullable=False),
    C("outcome", String, nullable=False),
    C("weight", Float, nullable=False),
    C("detector", String, nullable=False),
    C("context", String, nullable=False),
    C("observed_at", UTCDateTime, nullable=False),
    C("evidence_json", Text, nullable=False),
    C("taxonomy_version", Integer, nullable=False),
    C("created_at", UTCDateTime, nullable=False),
    CheckConstraint("weight > 0 AND weight <= 1", name="ck_observations_weight"),
    CheckConstraint(_in_list("outcome", Outcome), name="ck_observations_outcome"),
    CheckConstraint(_in_list("detector", Detector), name="ck_observations_detector"),
    CheckConstraint(_in_list("context", Context), name="ck_observations_context"),
)

profile_entries = Table(
    "profile_entries",
    metadata,
    C("error_key", String, primary_key=True),
    C("a", Float, nullable=False),
    C("b", Float, nullable=False),
    C("updated_at", UTCDateTime, nullable=False),
    C("p_hat", Float, nullable=False),
    C("ci_low", Float, nullable=False),
    C("ci_high", Float, nullable=False),
    C("n_eff", Float, nullable=False),
    C("status", String, nullable=False),
    C("last_seen_at", UTCDateTime, nullable=False),
    C("priority", Float, nullable=False),
    C("as_of", UTCDateTime, nullable=False),
    C("algo_version", Integer, nullable=False),
    C("taxonomy_version", Integer, nullable=False),
    CheckConstraint(_in_list("status", Status), name="ck_profile_entries_status"),
)

profile_snapshots = Table(
    "profile_snapshots",
    metadata,
    C("id", String, primary_key=True),
    C("session_id", String, ForeignKey("sessions.id"), nullable=True),
    C("reason", String, nullable=False),
    C("taken_at", UTCDateTime, nullable=False),
    C("as_of", UTCDateTime, nullable=False),
    C("algo_version", Integer, nullable=False),
    C("taxonomy_version", Integer, nullable=False),
    C("entries_json", Text, nullable=False),
    CheckConstraint(
        "reason IN ('rebuild', 'baseline', 'daily', 'retest')", name="ck_profile_snapshots_reason"
    ),
)

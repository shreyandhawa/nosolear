"""SQLite schema (ARCHITECTURE.md section 7) as SQLAlchemy Core tables."""

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


class UTCDateTime(TypeDecorator[datetime]):
    """Aware datetimes stored as ISO-8601 text in UTC (`...+00:00`); naive input is an error."""

    impl = String
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> str | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("datetime must be timezone-aware")
        return value.astimezone(UTC).isoformat(timespec="microseconds")

    def process_result_value(self, value: str | None, dialect: Dialect) -> datetime | None:
        return None if value is None else datetime.fromisoformat(value).astimezone(UTC)


metadata = MetaData()

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
    C("step", Integer, nullable=False),
    C("reference_text", Text, nullable=True),
    C("scripted", Boolean, nullable=False),
    C("created_at", UTCDateTime, nullable=False),
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

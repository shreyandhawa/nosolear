"""SQLite schema (ARCHITECTURE.md section 7) as SQLAlchemy Core tables."""

from collections.abc import Iterable
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Dialect,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    text,
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
    C("pack_id", String, nullable=False),
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
    C("pack_id", String, nullable=False),
    CheckConstraint(
        "reason IN ('rebuild', 'baseline', 'daily', 'retest')", name="ck_profile_snapshots_reason"
    ),
)

recordings = Table(
    "recordings",
    metadata,
    C("id", String, primary_key=True),
    C("attempt_id", String, ForeignKey("attempts.id"), nullable=False, unique=True),
    C("path", String, nullable=False, unique=True),
    C("duration_ms", Integer, nullable=False),
    C("sample_rate", Integer, nullable=False),
    C("sha256", String, nullable=False),
    C("created_at", UTCDateTime, nullable=False),
    CheckConstraint("path GLOB 'recordings/*.wav'", name="ck_recordings_path"),
    CheckConstraint("duration_ms >= 0", name="ck_recordings_duration"),
    CheckConstraint("sample_rate = 16000", name="ck_recordings_sample_rate"),
)

jobs = Table(
    "jobs",
    metadata,
    C("id", String, primary_key=True),
    C("kind", String, nullable=False),
    C("attempt_id", String, ForeignKey("attempts.id"), nullable=True),
    C("status", String, nullable=False),
    C("step", String, nullable=True),
    C("progress", Float, nullable=False),
    C("steps_json", Text, nullable=False),
    C("tries", Integer, nullable=False),
    C("created_at", UTCDateTime, nullable=False),
    C("updated_at", UTCDateTime, nullable=False),
    CheckConstraint("kind IN ('analyze', 'rescore')", name="ck_jobs_kind"),
    CheckConstraint("status IN ('queued', 'running', 'done', 'failed')", name="ck_jobs_status"),
    CheckConstraint("progress BETWEEN 0 AND 1", name="ck_jobs_progress"),
    CheckConstraint("tries >= 0", name="ck_jobs_tries"),
    Index("ix_jobs_status_created", "status", "created_at"),
)

usage_ledger = Table(
    "usage_ledger",
    metadata,
    C("id", Integer, primary_key=True, autoincrement=True),
    C("provider", String, nullable=False),
    C("unit", String, nullable=False),
    C("state", String, nullable=False),
    C("estimate", Integer, nullable=False),
    C("actual", Integer, nullable=True),
    C("period", String, nullable=False),
    C("job_id", String, ForeignKey("jobs.id"), nullable=True),
    C("created_at", UTCDateTime, nullable=False),
    C("settled_at", UTCDateTime, nullable=True),
    CheckConstraint("provider IN ('azure', 'anthropic')", name="ck_usage_ledger_provider"),
    CheckConstraint(
        "unit IN ('audio_seconds', 'tts_chars', 'tokens')", name="ck_usage_ledger_unit"
    ),
    CheckConstraint("state IN ('reserved', 'recorded', 'released')", name="ck_usage_ledger_state"),
    CheckConstraint("estimate >= 0", name="ck_usage_ledger_estimate"),
    CheckConstraint("(state = 'recorded') = (actual IS NOT NULL)", name="ck_usage_ledger_actual"),
    Index("ix_ledger_totals", "provider", "unit", "period", "state"),
)

tts_cache = Table(
    "tts_cache",
    metadata,
    C("hash", String, primary_key=True),
    C("text", Text, nullable=False),
    C("voice", String, nullable=False),
    C("rate", Integer, nullable=False),
    C("path", String, nullable=False),
    C("word_timings_json", Text, nullable=False),
    C("created_at", UTCDateTime, nullable=False),
    CheckConstraint("path = 'tts/' || hash || '.wav'", name="ck_tts_cache_path"),
)

# `tts_hash` and `calibration_run_id` get their foreign keys in 0d/0e, once those tables exist.
_ANALYSES_ATTEMPT_KEY = "attempt_id IS NOT NULL"
_ANALYSES_TTS_KEY = "attempt_id IS NULL"

analyses = Table(
    "analyses",
    metadata,
    C("id", Integer, primary_key=True, autoincrement=True),
    C("attempt_id", String, ForeignKey("attempts.id"), nullable=True),
    C("tts_hash", String, nullable=True),
    C("calibration_run_id", String, nullable=True),
    C("kind", String, nullable=False),
    C("provider", String, nullable=False),
    C("provider_version", String, nullable=False),
    C("adapter", String, nullable=False),
    C("adapter_version", Integer, nullable=False),
    C("raw_json", Text, nullable=False),
    C("created_at", UTCDateTime, nullable=False),
    CheckConstraint(
        "kind IN ('pronunciation', 'transcript', 'phone_probe', 'coach')", name="ck_analyses_kind"
    ),
    CheckConstraint(
        "(attempt_id IS NOT NULL AND tts_hash IS NULL AND calibration_run_id IS NULL) OR "
        "(attempt_id IS NULL AND tts_hash IS NOT NULL AND calibration_run_id IS NOT NULL)",
        name="ck_analyses_key_shape",
    ),
    Index(
        "uq_analyses_attempt_kind",
        "attempt_id",
        "kind",
        unique=True,
        sqlite_where=text(_ANALYSES_ATTEMPT_KEY),
    ),
    Index(
        "uq_analyses_tts_kind_run",
        "tts_hash",
        "kind",
        "calibration_run_id",
        unique=True,
        sqlite_where=text(_ANALYSES_TTS_KEY),
    ),
)

"""SQLAlchemy adapters for the storage ports."""

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import Engine, Row, delete, insert, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import Connection
from sqlalchemy.exc import IntegrityError

from nosolear.domain.analyses import AnalysisKind, NewAnalysis, StoredAnalysis
from nosolear.domain.estimates import BetaState, KeyEstimate
from nosolear.domain.jobs import Job, JobKind, JobStatus, initial_steps
from nosolear.domain.observations import Observation
from nosolear.domain.profile import Profile, ProfileEntry
from nosolear.domain.scoring import current_observations
from nosolear.domain.status import Status
from nosolear.domain.taxonomy import Taxonomy
from nosolear.persistence.job_queue import new_job_row
from nosolear.persistence.models import (
    analyses,
    attempts,
    format_utc,
    jobs,
    observations,
    profile_entries,
    profile_snapshots,
    recordings,
    sessions,
)
from nosolear.persistence.scoring_repository import (
    ExtractionRepository,
    observation_from_row,
    observation_rows,
    scoring_config_order,
)
from nosolear.ports.audio import (
    AttemptInfo,
    NewRecording,
    Recording,
    RecordingExists,
)
from nosolear.ports.clock import Clock


def _now() -> datetime:
    return datetime.now(UTC)


class ObservationRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def add_many(self, items: Sequence[Observation]) -> None:
        if not items:
            return
        rows = observation_rows(items, _now())
        with self._engine.begin() as conn:
            conn.execute(insert(observations), rows)

    def all(self) -> list[Observation]:
        stmt = select(observations).order_by(observations.c.observed_at, observations.c.id)
        with self._engine.connect() as conn:
            return [observation_from_row(r) for r in conn.execute(stmt)]

    def current(self) -> list[Observation]:
        """The observations the profile reads: per attempt, only the newest config's."""
        return current_observations(
            self.all(),
            scored=ExtractionRepository(self._engine).scored(),
            config_order=scoring_config_order(self._engine),
        )


def _entry_row(profile: Profile, e: ProfileEntry) -> dict[str, Any]:
    return {
        "error_key": e.definition.key,
        "a": e.state.a,
        "b": e.state.b,
        "updated_at": e.state.updated_at,
        "p_hat": e.estimate.p_hat,
        "ci_low": e.estimate.ci_low,
        "ci_high": e.estimate.ci_high,
        "n_eff": e.estimate.n_eff,
        "status": e.status.value,
        "last_seen_at": e.last_seen_at,
        "priority": e.priority,
        "provisional": e.provisional,
        "as_of": profile.as_of,
        "algo_version": profile.algo_version,
        "taxonomy_version": profile.taxonomy_version,
        "pack_id": profile.pack_id,
    }


def _snapshot_entry(row: dict[str, Any]) -> dict[str, Any]:
    stored = (
        "error_key",
        "a",
        "b",
        "p_hat",
        "ci_low",
        "ci_high",
        "n_eff",
        "status",
        "priority",
        "provisional",
    )
    return {
        **{k: row[k] for k in stored},
        "updated_at": format_utc(row["updated_at"]),
        "last_seen_at": format_utc(row["last_seen_at"]),
    }


def _insert_snapshot(
    conn: Connection,
    profile: Profile,
    rows: Sequence[dict[str, Any]],
    *,
    session_id: str | None,
    reason: str,
) -> str:
    snapshot_id = uuid4().hex
    conn.execute(
        insert(profile_snapshots).values(
            id=snapshot_id,
            session_id=session_id,
            reason=reason,
            taken_at=_now(),
            as_of=profile.as_of,
            algo_version=profile.algo_version,
            taxonomy_version=profile.taxonomy_version,
            entries_json=json.dumps([_snapshot_entry(r) for r in rows]),
            pack_id=profile.pack_id,
        )
    )
    return snapshot_id


def _restored_entry(taxonomy: Taxonomy, raw: dict[str, Any]) -> ProfileEntry:
    return ProfileEntry(
        definition=taxonomy.get(str(raw["error_key"])),
        state=BetaState(
            a=float(raw["a"]),
            b=float(raw["b"]),
            updated_at=datetime.fromisoformat(str(raw["updated_at"])),
        ),
        estimate=KeyEstimate(
            p_hat=float(raw["p_hat"]),
            ci_low=float(raw["ci_low"]),
            ci_high=float(raw["ci_high"]),
            n_eff=float(raw["n_eff"]),
        ),
        status=Status(str(raw["status"])),
        last_seen_at=datetime.fromisoformat(str(raw["last_seen_at"])),
        priority=float(raw["priority"]),
        provisional=bool(raw["provisional"]),
    )


class ProfileRepository:
    def __init__(self, engine: Engine, taxonomy: Taxonomy) -> None:
        self._engine = engine
        self._taxonomy = taxonomy

    def replace(self, profile: Profile) -> None:
        """Replace every current entry without a snapshot."""
        rows = [_entry_row(profile, e) for e in profile.entries]
        with self._engine.begin() as conn:
            conn.execute(delete(profile_entries))
            if rows:
                conn.execute(insert(profile_entries), rows)

    def save(self, profile: Profile, *, session_id: str | None, reason: str) -> str:
        """Replace every current entry and append a snapshot, atomically."""
        rows = [_entry_row(profile, e) for e in profile.entries]
        with self._engine.begin() as conn:
            conn.execute(delete(profile_entries))
            if rows:
                conn.execute(insert(profile_entries), rows)
            return _insert_snapshot(conn, profile, rows, session_id=session_id, reason=reason)

    def snapshot(self, profile: Profile, *, session_id: str | None, reason: str) -> str:
        """Append a snapshot and leave the current entries alone."""
        rows = [_entry_row(profile, e) for e in profile.entries]
        with self._engine.begin() as conn:
            return _insert_snapshot(conn, profile, rows, session_id=session_id, reason=reason)

    def latest_snapshot(self, session_id: str, reason: str) -> tuple[str, Profile] | None:
        """The newest snapshot of this session and reason, with its profile rebuilt from JSON."""
        stmt = (
            select(profile_snapshots)
            .where(
                profile_snapshots.c.session_id == session_id,
                profile_snapshots.c.reason == reason,
            )
            .order_by(profile_snapshots.c.taken_at.desc())
            .limit(1)
        )
        with self._engine.connect() as conn:
            row = conn.execute(stmt).first()
        if row is None:
            return None
        entries = tuple(
            _restored_entry(self._taxonomy, raw) for raw in json.loads(str(row.entries_json))
        )
        profile = Profile(
            as_of=row.as_of,
            taxonomy_version=row.taxonomy_version,
            algo_version=row.algo_version,
            pack_id=row.pack_id,
            entries=entries,
        )
        return str(row.id), profile

    def latest_pack_id(self) -> str | None:
        with self._engine.connect() as conn:
            return conn.execute(select(profile_entries.c.pack_id).limit(1)).scalar()

    def latest(self) -> Profile | None:
        stmt = select(profile_entries).order_by(
            profile_entries.c.priority.desc(), profile_entries.c.error_key
        )
        with self._engine.connect() as conn:
            rows = conn.execute(stmt).all()
        if not rows:
            return None
        entries = tuple(
            ProfileEntry(
                definition=self._taxonomy.get(r.error_key),
                state=BetaState(a=r.a, b=r.b, updated_at=r.updated_at),
                estimate=KeyEstimate(
                    p_hat=r.p_hat, ci_low=r.ci_low, ci_high=r.ci_high, n_eff=r.n_eff
                ),
                status=Status(r.status),
                last_seen_at=r.last_seen_at,
                priority=r.priority,
                provisional=r.provisional,
            )
            for r in rows
        )
        first = rows[0]
        return Profile(
            as_of=first.as_of,
            taxonomy_version=first.taxonomy_version,
            algo_version=first.algo_version,
            pack_id=first.pack_id,
            entries=entries,
        )


class AnalysisRepository:
    """Attempt-keyed analyses. Control rows keyed by TTS hash are added in Phase 0e."""

    def __init__(self, engine: Engine, clock: Clock) -> None:
        self._engine = engine
        self._clock = clock

    def get(self, attempt_id: str, kind: AnalysisKind) -> StoredAnalysis | None:
        with self._engine.connect() as conn:
            return _find_analysis(conn, attempt_id, kind)

    def put(self, analysis: NewAnalysis) -> StoredAnalysis:
        stmt = (
            sqlite_insert(analyses)
            .values(
                attempt_id=analysis.attempt_id,
                kind=analysis.kind.value,
                provider=analysis.provider,
                provider_version=analysis.provider_version,
                adapter=analysis.adapter,
                adapter_version=analysis.adapter_version,
                raw_json=json.dumps(dict(analysis.raw), sort_keys=True),
                created_at=self._clock.now(),
            )
            .on_conflict_do_nothing(
                index_elements=[analyses.c.attempt_id, analyses.c.kind],
                index_where=analyses.c.attempt_id.is_not(None),
            )
        )
        with self._engine.begin() as conn:
            conn.execute(stmt)
            stored = _find_analysis(conn, analysis.attempt_id, analysis.kind)
        if stored is None:
            raise RuntimeError("the analysis row was not written")
        return stored

    def for_attempt(self, attempt_id: str) -> list[StoredAnalysis]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                select(analyses).where(analyses.c.attempt_id == attempt_id).order_by(analyses.c.id)
            ).all()
        return [_analysis(row) for row in rows]


def _find_analysis(conn: Connection, attempt_id: str, kind: AnalysisKind) -> StoredAnalysis | None:
    row = conn.execute(
        select(analyses).where(analyses.c.attempt_id == attempt_id, analyses.c.kind == kind.value)
    ).first()
    return None if row is None else _analysis(row)


def _analysis(row: Row[Any]) -> StoredAnalysis:
    return StoredAnalysis(
        id=row.id,
        attempt_id=row.attempt_id,
        kind=AnalysisKind(row.kind),
        provider=row.provider,
        provider_version=row.provider_version,
        adapter=row.adapter,
        adapter_version=row.adapter_version,
        raw=json.loads(row.raw_json),
        created_at=row.created_at,
    )


_RECORDING_ATTEMPT_CONSTRAINT = "recordings.attempt_id"


def _recording(row: Row[Any]) -> Recording:
    return Recording(
        id=row.id,
        attempt_id=row.attempt_id,
        path=row.path,
        duration_ms=row.duration_ms,
        sample_rate=row.sample_rate,
        sha256=row.sha256,
    )


class RecordingRepository:
    """Recordings rows; the matching ANALYZE job is inserted in the same transaction."""

    def __init__(self, engine: Engine, clock: Clock) -> None:
        self._engine = engine
        self._clock = clock

    def add_and_enqueue(self, new: NewRecording) -> tuple[Recording, Job]:
        now = self._clock.now()
        recording_id = uuid4().hex
        job_row = new_job_row(JobKind.ANALYZE, new.attempt_id, now)
        try:
            with self._engine.begin() as conn:
                conn.execute(
                    insert(recordings).values(
                        id=recording_id,
                        attempt_id=new.attempt_id,
                        path=new.stored.path,
                        duration_ms=new.stored.duration_ms,
                        sample_rate=new.stored.sample_rate,
                        sha256=new.stored.sha256,
                        created_at=now,
                    )
                )
                conn.execute(insert(jobs).values(**job_row))
        except IntegrityError as exc:
            if _RECORDING_ATTEMPT_CONSTRAINT in str(exc.orig):
                raise RecordingExists("This attempt already has a recording.") from None
            raise
        recording = Recording(
            id=recording_id,
            attempt_id=new.attempt_id,
            path=new.stored.path,
            duration_ms=new.stored.duration_ms,
            sample_rate=new.stored.sample_rate,
            sha256=new.stored.sha256,
        )
        job = Job(
            id=job_row["id"],
            kind=JobKind.ANALYZE,
            attempt_id=new.attempt_id,
            status=JobStatus.QUEUED,
            step=None,
            progress=0.0,
            steps=initial_steps(JobKind.ANALYZE),
            tries=0,
            created_at=now,
            updated_at=now,
        )
        return recording, job

    def for_attempt(self, attempt_id: str) -> Recording | None:
        with self._engine.connect() as conn:
            row = conn.execute(
                select(recordings).where(recordings.c.attempt_id == attempt_id)
            ).first()
        return None if row is None else _recording(row)


class AttemptRepository:
    """Sessions and attempts: the attempt reader for uploads and analyses, and the creator the
    CLI's `--new-attempt` uses."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def exists(self, attempt_id: str) -> bool:
        with self._engine.connect() as conn:
            row = conn.execute(select(attempts.c.id).where(attempts.c.id == attempt_id)).first()
        return row is not None

    def get(self, attempt_id: str) -> AttemptInfo | None:
        with self._engine.connect() as conn:
            row = conn.execute(select(attempts).where(attempts.c.id == attempt_id)).first()
        if row is None:
            return None
        return AttemptInfo(
            id=row.id,
            session_id=row.session_id,
            step=row.step,
            reference_text=row.reference_text,
            scripted=row.scripted,
        )

    def create_attempt(
        self,
        *,
        session_kind: str,
        step: str,
        reference_text: str | None,
        scripted: bool,
        now: datetime,
    ) -> str:
        session_id = uuid4().hex
        attempt_id = uuid4().hex
        with self._engine.begin() as conn:
            conn.execute(
                insert(sessions).values(
                    id=session_id,
                    kind=session_kind,
                    protocol_version=1,
                    started_at=now,
                    completed_at=None,
                )
            )
            conn.execute(
                insert(attempts).values(
                    id=attempt_id,
                    session_id=session_id,
                    step=step,
                    reference_text=reference_text,
                    scripted=scripted,
                    created_at=now,
                )
            )
        return attempt_id

"""In-memory fakes for the ports. Domain builders live in factories.py."""

from __future__ import annotations

import hashlib
import threading
import uuid
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime
from pathlib import Path

from nosolear.app.steps import StepContext
from nosolear.domain.analyses import AnalysisKind, NewAnalysis, StoredAnalysis
from nosolear.domain.audio import (
    DEFAULT_LIMITS,
    TARGET_RATE,
    AudioLimits,
    duration_ms,
    encode_wav,
    parse_wav,
    to_16k,
)
from nosolear.domain.budget import Caps, Provider, Unit, Usage, fits, period_for
from nosolear.domain.daily_plan import DailyPlan, PromptCandidate
from nosolear.domain.errors import CapExceeded, InvalidAudio
from nosolear.domain.jobs import (
    Job,
    JobKind,
    JobStatus,
    StepRecord,
    initial_steps,
    progress_of,
    recover_running,
    resume_plan,
)
from nosolear.domain.profile import Profile
from nosolear.domain.rechecks import RecheckState
from nosolear.domain.taxonomy import Skill
from nosolear.ports.audio import (
    AttemptInfo,
    NewRecording,
    PendingUpload,
    Recording,
    RecordingExists,
    StoredRecording,
    is_recording_path,
)
from nosolear.ports.clock import Clock
from nosolear.ports.jobs import JobNotResumable, UnknownJob
from nosolear.ports.ledger import LedgerError, Reservation
from nosolear.ports.plan import AttemptRef, StartedSession, StoredPlan


class _FakeUpload:
    def __init__(self, store: FakeAudioStore) -> None:
        self._store = store
        self._chunks: list[bytes] = []
        self._size = 0
        self._finished = False

    def write(self, chunk: bytes) -> None:
        if self._finished:
            raise RuntimeError("The upload is already finished.")
        self._size += len(chunk)
        if self._size > self._store.limits.max_bytes:
            self.abort()
            raise InvalidAudio("too_large")
        self._chunks.append(chunk)

    def commit(self) -> StoredRecording:
        if self._finished:
            raise RuntimeError("The upload is already finished.")
        data = b"".join(self._chunks)
        self.abort()
        audio = parse_wav(data, self._store.limits)
        samples = to_16k(audio)
        if len(samples) == 0:
            raise InvalidAudio("empty")
        encoded = encode_wav(samples, TARGET_RATE)
        path = f"recordings/{uuid.uuid4()}.wav"
        self._store.files[path] = encoded
        return StoredRecording(
            path=path,
            duration_ms=duration_ms(len(samples), TARGET_RATE),
            sample_rate=TARGET_RATE,
            sha256=hashlib.sha256(encoded).hexdigest(),
        )

    def abort(self) -> None:
        self._finished = True
        self._chunks = []


class FakeAudioStore:
    def __init__(self, limits: AudioLimits = DEFAULT_LIMITS) -> None:
        self.limits = limits
        self.files: dict[str, bytes] = {}

    def begin_upload(self) -> PendingUpload:
        return _FakeUpload(self)

    def read(self, path: str) -> bytes:
        self.resolve(path)
        return self.files[path]

    def resolve(self, path: str) -> Path:
        if not is_recording_path(path):
            raise ValueError("Not a stored recording path.")
        return Path("/fake-audio-store") / path

    def delete(self, path: str) -> None:
        self.resolve(path)
        self.files.pop(path, None)


@dataclass
class _LedgerRow:
    provider: Provider
    unit: Unit
    period: str
    estimate: int
    state: str  # "reserved" | "recorded" | "released"
    actual: int | None


class FakeUsageLedger:
    """The usage ledger in memory, with the same `fits` and `period_for` arithmetic as SQLite."""

    def __init__(self, caps: Caps, clock: Clock) -> None:
        self._caps = caps
        self._clock = clock
        self._rows: dict[int, _LedgerRow] = {}
        self._next_id = 1

    def reserve(
        self, provider: Provider, unit: Unit, estimate: int, *, job_id: str | None = None
    ) -> Reservation:
        cap = self._caps.limit(provider, unit)
        if estimate < 0:
            raise ValueError("estimate must not be negative")
        period = period_for(provider, unit, self._clock.now())
        recorded, reserved = self._totals(provider, unit, period)
        if not fits(cap, recorded, reserved, estimate):
            raise CapExceeded()
        reservation_id = self._next_id
        self._next_id += 1
        self._rows[reservation_id] = _LedgerRow(provider, unit, period, estimate, "reserved", None)
        return Reservation(
            id=reservation_id, provider=provider, unit=unit, estimate=estimate, period=period
        )

    def record(self, reservation: Reservation, actual: int) -> None:
        if actual < 0:
            raise ValueError("actual must not be negative")
        row = self._open(reservation)
        row.state, row.actual = "recorded", actual

    def release(self, reservation: Reservation) -> None:
        self._open(reservation).state = "released"

    def settle_open_reservations(self) -> int:
        open_rows = [row for row in self._rows.values() if row.state == "reserved"]
        for row in open_rows:
            row.state, row.actual = "recorded", row.estimate
        return len(open_rows)

    def usage(self, provider: Provider, unit: Unit) -> Usage:
        period = period_for(provider, unit, self._clock.now())
        recorded, reserved = self._totals(provider, unit, period)
        return Usage(
            provider=provider,
            unit=unit,
            period=period,
            recorded=recorded,
            reserved=reserved,
            cap=self._caps.limit(provider, unit),
        )

    def _open(self, reservation: Reservation) -> _LedgerRow:
        row = self._rows.get(reservation.id)
        if row is None or row.state != "reserved":
            raise LedgerError("the reservation is not open")
        return row

    def _totals(self, provider: Provider, unit: Unit, period: str) -> tuple[int, int]:
        mine = [
            row
            for row in self._rows.values()
            if row.provider is provider and row.unit is unit and row.period == period
        ]
        recorded = sum(row.actual or 0 for row in mine if row.state == "recorded")
        reserved = sum(row.estimate for row in mine if row.state == "reserved")
        return recorded, reserved


class FakePaidPort:
    """A raw paid adapter stand-in. `run` counts every attempt, even one that fails."""

    layer = "raw"

    def __init__(self) -> None:
        self.calls = 0
        self.fail_with: Exception | None = None

    def run(self, units: int) -> int:
        self.calls += 1
        if self.fail_with is not None:
            raise self.fail_with
        return units


@dataclass(frozen=True, slots=True)
class JobUpdate:
    """One `FakeJobQueue.update` call, as it was made."""

    job_id: str
    steps: tuple[StepRecord, ...]
    step: str | None
    progress: float
    status: JobStatus | None


class FakeJobQueue:
    """The job queue in memory, with the same transitions as `SqliteJobQueue`. Thread-safe."""

    def __init__(self, clock: Clock) -> None:
        self._clock = clock
        self._jobs: dict[str, Job] = {}  # insertion order is creation order (FIFO claims)
        self._lock = threading.Lock()
        self.updates: list[JobUpdate] = []

    def enqueue(self, kind: JobKind, attempt_id: str | None) -> Job:
        now = self._clock.now()
        job = Job(
            id=uuid.uuid4().hex,
            kind=kind,
            attempt_id=attempt_id,
            status=JobStatus.QUEUED,
            step=None,
            progress=0.0,
            steps=initial_steps(kind),
            tries=0,
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            self._jobs[job.id] = job
        return job

    def claim_next(self) -> Job | None:
        now = self._clock.now()
        with self._lock:
            for job in self._jobs.values():
                if job.status is JobStatus.QUEUED:
                    claimed = replace(
                        job, status=JobStatus.RUNNING, tries=job.tries + 1, updated_at=now
                    )
                    self._jobs[job.id] = claimed
                    return claimed
        return None

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def update(
        self,
        job_id: str,
        *,
        steps: Sequence[StepRecord],
        step: str | None,
        progress: float,
        status: JobStatus | None = None,
    ) -> None:
        now = self._clock.now()
        with self._lock:
            job = self._require(job_id)
            self._jobs[job_id] = replace(
                job,
                steps=tuple(steps),
                step=step,
                progress=progress,
                status=job.status if status is None else status,
                updated_at=now,
            )
            self.updates.append(JobUpdate(job_id, tuple(steps), step, progress, status))

    def resume(self, job_id: str) -> Job:
        now = self._clock.now()
        with self._lock:
            job = self._require(job_id)
            if job.status is not JobStatus.FAILED:
                raise JobNotResumable("Only a failed job can be resumed.")
            steps = resume_plan(job.kind, job.steps)
            resumed = replace(
                job,
                status=JobStatus.QUEUED,
                steps=steps,
                step=None,
                progress=progress_of(steps),
                updated_at=now,
            )
            self._jobs[job_id] = resumed
            return resumed

    def requeue_running(self) -> int:
        now = self._clock.now()
        moved = 0
        with self._lock:
            for job in list(self._jobs.values()):
                if job.status is JobStatus.RUNNING:
                    steps = recover_running(job.steps)
                    self._jobs[job.id] = replace(
                        job,
                        status=JobStatus.QUEUED,
                        steps=steps,
                        step=None,
                        progress=progress_of(steps),
                        updated_at=now,
                    )
                    moved += 1
        return moved

    def _require(self, job_id: str) -> Job:
        job = self._jobs.get(job_id)
        if job is None:
            raise UnknownJob("No job has this id.")
        return job


class FakeAnalysisStore:
    """The analysis store in memory: idempotent on (attempt_id, kind), like the SQLite table."""

    def __init__(self, clock: Clock) -> None:
        self._clock = clock
        self._rows: dict[tuple[str, AnalysisKind], StoredAnalysis] = {}
        self._next_id = 1

    def get(self, attempt_id: str, kind: AnalysisKind) -> StoredAnalysis | None:
        return self._rows.get((attempt_id, kind))

    def put(self, analysis: NewAnalysis) -> StoredAnalysis:
        key = (analysis.attempt_id, analysis.kind)
        existing = self._rows.get(key)
        if existing is not None:
            return existing
        stored = StoredAnalysis(
            id=self._next_id,
            attempt_id=analysis.attempt_id,
            kind=analysis.kind,
            provider=analysis.provider,
            provider_version=analysis.provider_version,
            adapter=analysis.adapter,
            adapter_version=analysis.adapter_version,
            raw=dict(analysis.raw),
            created_at=self._clock.now(),
        )
        self._next_id += 1
        self._rows[key] = stored
        return stored

    def for_attempt(self, attempt_id: str) -> list[StoredAnalysis]:
        return [row for (owner, _), row in self._rows.items() if owner == attempt_id]


class FakeStep:
    """A `Step` that records every context it runs with. `raises` and `on_run` act on each run."""

    def __init__(
        self,
        name: str,
        *,
        applies: bool = True,
        raises: Exception | None = None,
        on_run: Callable[[StepContext], None] | None = None,
    ) -> None:
        self.name = name
        self.applies_to = applies
        self.raises = raises
        self.on_run = on_run
        self.runs: list[StepContext] = []

    def applies(self, ctx: StepContext) -> bool:
        return self.applies_to

    def run(self, ctx: StepContext) -> None:
        self.runs.append(ctx)
        if self.on_run is not None:
            self.on_run(ctx)
        if self.raises is not None:
            raise self.raises


class FakeProfileStore:
    """A `ProfileStore` in memory. `stored_pack_id` is what it reports before anything is saved."""

    def __init__(self, stored_pack_id: str | None = None) -> None:
        self._seed_pack_id = stored_pack_id
        self.saved: list[tuple[Profile, str | None, str]] = []
        self.replaced: list[Profile] = []

    def save(self, profile: Profile, *, session_id: str | None, reason: str) -> str:
        self.saved.append((profile, session_id, reason))
        return f"snapshot-{len(self.saved)}"

    def replace(self, profile: Profile) -> None:
        self.replaced.append(profile)

    def snapshot(self, profile: Profile, *, session_id: str | None, reason: str) -> str:
        self.saved.append((profile, session_id, reason))
        return f"snapshot-{len(self.saved)}"

    def latest_pack_id(self) -> str | None:
        return self.saved[-1][0].pack_id if self.saved else self._seed_pack_id


class FakeAttemptReader:
    """Attempts in memory. Tests register the ones they need with `add`."""

    def __init__(self, attempts: Sequence[AttemptInfo] = ()) -> None:
        self._attempts = {a.id: a for a in attempts}

    def add(self, attempt: AttemptInfo) -> None:
        self._attempts[attempt.id] = attempt

    def exists(self, attempt_id: str) -> bool:
        return attempt_id in self._attempts

    def get(self, attempt_id: str) -> AttemptInfo | None:
        return self._attempts.get(attempt_id)


class FakeRecordingStore:
    """Recordings in memory, enqueuing into a `FakeJobQueue` like the SQLite transaction does."""

    def __init__(self, jobs: FakeJobQueue) -> None:
        self._jobs = jobs
        self._rows: dict[str, Recording] = {}

    def add_and_enqueue(self, new: NewRecording) -> tuple[Recording, Job]:
        if new.attempt_id in self._rows:
            raise RecordingExists("This attempt already has a recording.")
        recording = Recording(
            id=uuid.uuid4().hex,
            attempt_id=new.attempt_id,
            path=new.stored.path,
            duration_ms=new.stored.duration_ms,
            sample_rate=new.stored.sample_rate,
            sha256=new.stored.sha256,
        )
        job = self._jobs.enqueue(JobKind.ANALYZE, new.attempt_id)
        self._rows[new.attempt_id] = recording
        return recording, job

    def for_attempt(self, attempt_id: str) -> Recording | None:
        return self._rows.get(attempt_id)


class FakeDailyPlanStore:
    """`DailyPlanStore` in memory: the first plan for a date wins, as the UNIQUE column does."""

    def __init__(self) -> None:
        self.plans: dict[date, StoredPlan] = {}

    def get(self, for_date: date) -> StoredPlan | None:
        return self.plans.get(for_date)

    def add(self, plan: DailyPlan) -> StoredPlan:
        existing = self.plans.get(plan.for_date)
        if existing is not None:
            return existing
        stored = StoredPlan(id=uuid.uuid4().hex, plan=plan)
        self.plans[plan.for_date] = stored
        return stored

    def _recent(self, before: date, limit: int) -> list[StoredPlan]:
        days = sorted((d for d in self.plans if d < before), reverse=True)[:limit]
        return [self.plans[d] for d in days]

    def recent_focus_keys(self, before: date, limit: int = 3) -> dict[Skill, list[str]]:
        keys: dict[Skill, list[str]] = {}
        for stored in self._recent(before, limit):
            for focus in stored.plan.foci:
                keys.setdefault(focus.skill, []).append(focus.error_key)
        return keys

    def recent_prompt_ids(self, before: date, limit: int = 3) -> list[str]:
        ids = [s.plan.prompt.id for s in self._recent(before, limit) if s.plan.prompt is not None]
        return ids


class FakeProfileReader:
    def __init__(self, profile: Profile | None = None) -> None:
        self.profile = profile

    def latest(self) -> Profile | None:
        return self.profile


class FakeRecheckStore:
    def __init__(self, states: dict[str, RecheckState] | None = None) -> None:
        self.states: dict[str, RecheckState] = dict(states or {})

    def load(self) -> dict[str, RecheckState]:
        return dict(self.states)

    def save(self, states: Mapping[str, RecheckState]) -> None:
        self.states = dict(states)


class FakePromptBank:
    def __init__(self, prompts: Sequence[PromptCandidate] = ()) -> None:
        self.items = list(prompts)

    def prompts(self) -> list[PromptCandidate]:
        return list(self.items)


class FakeScoredKeys:
    """Every key is scored unless it is named in `unscored`."""

    def __init__(self, unscored: Iterable[str] = ()) -> None:
        self.unscored = frozenset(unscored)

    def is_scored(self, error_key: str) -> bool:
        return error_key not in self.unscored


class FakeDailySessionStore:
    """`DailySessionStore` in memory: one session per plan, as the unique `plan_id` index does."""

    def __init__(self) -> None:
        self.sessions: dict[str, StartedSession] = {}
        self.created: list[StartedSession] = []

    def for_plan(self, plan_id: str) -> StartedSession | None:
        found = self.sessions.get(plan_id)
        return None if found is None else replace(found, created=False)

    def create(
        self, *, plan_id: str, prompt_item_id: str | None, started_at: datetime
    ) -> StartedSession:
        started = StartedSession(
            session_id=uuid.uuid4().hex,
            plan_id=plan_id,
            created=True,
            attempts=(
                AttemptRef(
                    id=uuid.uuid4().hex,
                    step="speak",
                    reference_text=None,
                    content_item_id=prompt_item_id,
                ),
            ),
        )
        self.sessions[plan_id] = started
        self.created.append(started)
        return started

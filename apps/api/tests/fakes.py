"""In-memory fakes for the ports. Domain builders live in factories.py."""

from __future__ import annotations

import hashlib
import threading
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path

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
from nosolear.ports.audio import PendingUpload, StoredRecording, is_recording_path
from nosolear.ports.clock import Clock
from nosolear.ports.jobs import JobNotResumable, UnknownJob
from nosolear.ports.ledger import LedgerError, Reservation


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

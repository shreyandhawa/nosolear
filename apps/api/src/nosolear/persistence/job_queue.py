"""SQLite job queue (ARCHITECTURE.md section 13, Phase 0c).

Claims and resumes run under `BEGIN IMMEDIATE`, so the select-and-update is atomic across threads
and processes. The steps helpers are module-level so the step writer can reuse one encoding.
"""

import dataclasses
import json
import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import Engine, Row, select, text, update
from sqlalchemy.engine import Connection

from nosolear.domain.jobs import (
    Job,
    JobKind,
    JobStatus,
    StepRecord,
    StepState,
    initial_steps,
    progress_of,
    recover_running,
    resume_plan,
)
from nosolear.persistence.models import jobs
from nosolear.persistence.transactions import immediate
from nosolear.ports.clock import Clock
from nosolear.ports.jobs import JobNotResumable, UnknownJob

# Equal `created_at` values (a frozen clock, or the same microsecond) fall back to insertion order.
_FIFO = (jobs.c.created_at, text("rowid"))


def steps_to_json(steps: Sequence[StepRecord]) -> str:
    """The only encoding of `steps_json`: the four safe fields per step, nothing else."""
    return json.dumps(
        [
            {
                "name": step.name,
                "state": step.state.value,
                "error_code": step.error_code,
                "message": step.message,
            }
            for step in steps
        ]
    )


def steps_from_json(text: str) -> tuple[StepRecord, ...]:
    return tuple(
        StepRecord(
            name=item["name"],
            state=StepState(item["state"]),
            error_code=item["error_code"],
            message=item["message"],
        )
        for item in json.loads(text)
    )


def new_job_row(kind: JobKind, attempt_id: str | None, now: datetime) -> dict[str, Any]:
    """The column values for a freshly enqueued job."""
    return {
        "id": uuid.uuid4().hex,
        "kind": kind.value,
        "attempt_id": attempt_id,
        "status": JobStatus.QUEUED.value,
        "step": None,
        "progress": 0.0,
        "steps_json": steps_to_json(initial_steps(kind)),
        "tries": 0,
        "created_at": now,
        "updated_at": now,
    }


def _job(row: Row[Any]) -> Job:
    return Job(
        id=row.id,
        kind=JobKind(row.kind),
        attempt_id=row.attempt_id,
        status=JobStatus(row.status),
        step=row.step,
        progress=row.progress,
        steps=steps_from_json(row.steps_json),
        tries=row.tries,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _fetch(conn: Connection, job_id: str) -> Job | None:
    row = conn.execute(select(jobs).where(jobs.c.id == job_id)).first()
    return None if row is None else _job(row)


class SqliteJobQueue:
    def __init__(self, engine: Engine, *, clock: Clock) -> None:
        self._engine = engine
        self._clock = clock

    def enqueue(self, kind: JobKind, attempt_id: str | None) -> Job:
        now = self._clock.now()
        row = new_job_row(kind, attempt_id, now)
        with self._engine.begin() as conn:
            conn.execute(jobs.insert().values(**row))
        return Job(
            id=row["id"],
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

    def claim_next(self) -> Job | None:
        now = self._clock.now()
        with immediate(self._engine) as conn:
            row = conn.execute(
                select(jobs)
                .where(jobs.c.status == JobStatus.QUEUED.value)
                .order_by(*_FIFO)
                .limit(1)
            ).first()
            if row is None:
                return None
            conn.execute(
                update(jobs)
                .where(jobs.c.id == row.id)
                .values(status=JobStatus.RUNNING.value, tries=jobs.c.tries + 1, updated_at=now)
            )
            return dataclasses.replace(
                _job(row), status=JobStatus.RUNNING, tries=row.tries + 1, updated_at=now
            )

    def get(self, job_id: str) -> Job | None:
        with self._engine.connect() as conn:
            return _fetch(conn, job_id)

    def update(
        self,
        job_id: str,
        *,
        steps: Sequence[StepRecord],
        step: str | None,
        progress: float,
        status: JobStatus | None = None,
    ) -> None:
        values: dict[str, Any] = {
            "steps_json": steps_to_json(steps),
            "step": step,
            "progress": progress,
            "updated_at": self._clock.now(),
        }
        if status is not None:
            values["status"] = status.value
        with self._engine.begin() as conn:
            result = conn.execute(update(jobs).where(jobs.c.id == job_id).values(**values))
            if result.rowcount == 0:
                raise UnknownJob("No job has this id.")

    def resume(self, job_id: str) -> Job:
        now = self._clock.now()
        with immediate(self._engine) as conn:
            job = _fetch(conn, job_id)
            if job is None:
                raise UnknownJob("No job has this id.")
            if job.status is not JobStatus.FAILED:
                raise JobNotResumable("Only a failed job can be resumed.")
            steps = resume_plan(job.kind, job.steps)
            progress = progress_of(steps)
            conn.execute(
                update(jobs)
                .where(jobs.c.id == job_id)
                .values(
                    status=JobStatus.QUEUED.value,
                    steps_json=steps_to_json(steps),
                    step=None,
                    progress=progress,
                    updated_at=now,
                )
            )
        return dataclasses.replace(
            job,
            status=JobStatus.QUEUED,
            steps=steps,
            step=None,
            progress=progress,
            updated_at=now,
        )

    def requeue_running(self) -> int:
        now = self._clock.now()
        with immediate(self._engine) as conn:
            running = [
                _job(row)
                for row in conn.execute(
                    select(jobs).where(jobs.c.status == JobStatus.RUNNING.value)
                )
            ]
            for job in running:
                steps = recover_running(job.steps)
                conn.execute(
                    update(jobs)
                    .where(jobs.c.id == job.id)
                    .values(
                        status=JobStatus.QUEUED.value,
                        steps_json=steps_to_json(steps),
                        step=None,
                        progress=progress_of(steps),
                        updated_at=now,
                    )
                )
        return len(running)

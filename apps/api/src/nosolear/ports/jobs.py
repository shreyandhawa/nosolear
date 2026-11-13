"""The job queue port: enqueue, claim, update, resume and startup recovery."""

from collections.abc import Sequence
from typing import Protocol

from nosolear.domain.jobs import Job, JobKind, JobStatus, StepRecord


class JobNotResumable(ValueError):
    """`resume` was called on a job that is not FAILED."""


class UnknownJob(ValueError):
    """No job has this id."""


class JobQueue(Protocol):
    def enqueue(self, kind: JobKind, attempt_id: str | None) -> Job:
        """A QUEUED job with its steps from `initial_steps`."""
        ...

    def claim_next(self) -> Job | None:
        """Atomically takes the oldest QUEUED job, marks it RUNNING and counts a try."""
        ...

    def get(self, job_id: str) -> Job | None: ...

    def update(
        self,
        job_id: str,
        *,
        steps: Sequence[StepRecord],
        step: str | None,
        progress: float,
        status: JobStatus | None = None,
    ) -> None:
        """Raises `UnknownJob` if the id is not stored."""
        ...

    def resume(self, job_id: str) -> Job:
        """FAILED -> QUEUED with `resume_plan`. Raises `JobNotResumable` otherwise."""
        ...

    def requeue_running(self) -> int:
        """Startup: RUNNING -> QUEUED with `recover_running`. Returns how many jobs moved."""
        ...

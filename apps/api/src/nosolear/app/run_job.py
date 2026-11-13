"""The job runner: runs a job's plan in order and persists every step change.

Step failures never escape: they become FAILED or BLOCKED steps. Only the queue itself can raise.
"""

import logging
from collections.abc import Callable

from nosolear.app.steps import StepContext, StepRegistry, running_job
from nosolear.domain.errors import NosolearError
from nosolear.domain.jobs import (
    JOB_PLANS,
    Job,
    JobStatus,
    StepRecord,
    StepState,
    final_status,
    progress_of,
)
from nosolear.ports.jobs import JobQueue, UnknownJob

logger = logging.getLogger(__name__)

INTERNAL_ERROR = "internal_error"
INTERNAL_MESSAGE = "The step failed unexpectedly."
BLOCKED_MESSAGE = "A step this one needs did not finish."
_SETTLED = frozenset({StepState.DONE, StepState.SKIPPED, StepState.FAILED, StepState.BLOCKED})
_BAD = frozenset({StepState.FAILED, StepState.BLOCKED})


def run_job(*, job_id: str, jobs: JobQueue, registry: StepRegistry) -> Job:
    job = jobs.get(job_id)
    if job is None:
        raise UnknownJob("No job has this id.")
    specs = JOB_PLANS[job.kind]
    records: dict[str, StepRecord] = {step.name: step for step in job.steps}

    def ordered() -> tuple[StepRecord, ...]:
        return tuple(records[spec.name] for spec in specs)

    def write(
        step: str | None, *, progress: float | None = None, status: JobStatus | None = None
    ) -> None:
        jobs.update(
            job_id,
            steps=ordered(),
            step=step,
            progress=progress_of(ordered()) if progress is None else progress,
            status=status,
        )

    def reporter(name: str) -> Callable[[float], None]:
        def report(fraction: float) -> None:
            if not 0.0 <= fraction <= 1.0:
                raise ValueError("step progress must be within 0..1")
            settled = sum(1 for record in records.values() if record.state in _SETTLED)
            write(name, progress=(settled + fraction) / len(specs))

        return report

    for spec in specs:
        name = spec.name
        if records[name].state in (StepState.DONE, StepState.SKIPPED):
            continue
        if any(records[need].state in _BAD for need in spec.needs):
            records[name] = StepRecord(
                name, StepState.BLOCKED, error_code="blocked", message=BLOCKED_MESSAGE
            )
            write(name)
            continue
        step = registry.get(job.kind, name)
        if step is None:
            records[name] = StepRecord(name, StepState.SKIPPED, message="not_available")
            write(name)
            continue
        ctx = StepContext(
            job_id=job_id, kind=job.kind, attempt_id=job.attempt_id, progress=reporter(name)
        )
        try:
            applicable = step.applies(ctx)
        except Exception as error:
            records[name] = _failure(name, error)
            write(name)
            continue
        if not applicable:
            records[name] = StepRecord(name, StepState.SKIPPED, message="not_applicable")
            write(name)
            continue
        records[name] = StepRecord(name, StepState.RUNNING)
        write(name)
        try:
            with running_job(job_id):
                step.run(ctx)
        except Exception as error:
            records[name] = _failure(name, error)
        else:
            records[name] = StepRecord(name, StepState.DONE)
        write(name)

    write(None, status=final_status(ordered()))
    finished = jobs.get(job_id)
    if finished is None:
        raise UnknownJob("No job has this id.")
    return finished


def _failure(name: str, error: Exception) -> StepRecord:
    if isinstance(error, NosolearError):
        return StepRecord(name, StepState.FAILED, error_code=error.code, message=error.safe_message)
    # Only the exception type is logged: its message may carry input bytes or a key.
    logger.error("step failed: %s", type(error).__name__)
    return StepRecord(name, StepState.FAILED, error_code=INTERNAL_ERROR, message=INTERNAL_MESSAGE)

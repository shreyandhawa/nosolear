"""Job plans and step states for the job runner. Pure: no I/O, no clock reads.

A job runs its plan in order. A step whose `needs` failed is BLOCKED; a step whose `uses` re-ran
is re-run on resume (ARCHITECTURE.md section 13, Phase 0c).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class JobKind(StrEnum):
    ANALYZE = "analyze"
    RESCORE = "rescore"
    CALIBRATE = "calibrate"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class StepState(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    SKIPPED = "skipped"
    FAILED = "failed"
    BLOCKED = "blocked"


_SETTLED = frozenset({StepState.DONE, StepState.SKIPPED, StepState.FAILED, StepState.BLOCKED})
_BAD = frozenset({StepState.FAILED, StepState.BLOCKED})


@dataclass(frozen=True, slots=True)
class StepSpec:
    name: str
    needs: tuple[str, ...] = ()  # hard: BLOCKED if a needed step failed or is blocked
    uses: tuple[str, ...] = ()  # soft: runs regardless, but is re-run on resume if these re-ran


JOB_PLANS: dict[JobKind, tuple[StepSpec, ...]] = {
    JobKind.ANALYZE: (
        StepSpec("score"),
        StepSpec("transcribe"),
        StepSpec("probe"),
        StepSpec("coach", needs=("transcribe",)),
        StepSpec("extract", uses=("score", "transcribe", "probe", "coach")),
    ),
    JobKind.RESCORE: (StepSpec("extract"),),
    JobKind.CALIBRATE: (
        StepSpec("controls"),
        StepSpec("evaluate", needs=("controls",)),
        StepSpec("queue_rescore", needs=("evaluate",)),
    ),
}


@dataclass(frozen=True, slots=True)
class StepRecord:
    name: str
    state: StepState = StepState.PENDING
    error_code: str | None = None  # NosolearError.code, or "internal_error"
    message: str | None = None  # safe message only; also skip reasons ("not_applicable", ...)


@dataclass(frozen=True, slots=True)
class Job:
    id: str
    kind: JobKind
    attempt_id: str | None
    status: JobStatus
    step: str | None
    progress: float
    steps: tuple[StepRecord, ...]
    tries: int
    created_at: datetime
    updated_at: datetime


def initial_steps(kind: JobKind) -> tuple[StepRecord, ...]:
    return tuple(StepRecord(spec.name) for spec in JOB_PLANS[kind])


def progress_of(steps: Sequence[StepRecord]) -> float:
    """The share of steps that have settled: DONE, SKIPPED, FAILED or BLOCKED."""
    if not steps:
        return 0.0
    return sum(1 for s in steps if s.state in _SETTLED) / len(steps)


def final_status(steps: Sequence[StepRecord]) -> JobStatus:
    return JobStatus.FAILED if any(s.state in _BAD for s in steps) else JobStatus.DONE


def resume_plan(kind: JobKind, steps: Sequence[StepRecord]) -> tuple[StepRecord, ...]:
    """Reset every FAILED or BLOCKED step, and every step that needs or uses a reset step.

    `steps` is in plan order, so a dependency is always decided before its dependents. DONE and
    SKIPPED steps outside that closure are returned unchanged.
    """
    specs = {spec.name: spec for spec in JOB_PLANS[kind]}
    reset: set[str] = set()
    out: list[StepRecord] = []
    for step in steps:
        spec = specs[step.name]
        if step.state in _BAD or set(spec.needs + spec.uses) & reset:
            reset.add(step.name)
            out.append(StepRecord(step.name))
        else:
            out.append(step)
    return tuple(out)


def recover_running(steps: Sequence[StepRecord]) -> tuple[StepRecord, ...]:
    """A RUNNING step (left by a crash) becomes PENDING with its error fields cleared."""
    return tuple(StepRecord(s.name) if s.state is StepState.RUNNING else s for s in steps)

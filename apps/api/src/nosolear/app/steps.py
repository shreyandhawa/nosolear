"""The step interface that Phases 0d and 0e plug into: a registry of named steps per job kind.

A step's name and its `needs`/`uses` come from `JOB_PLANS`; steps never redefine them.
"""

from collections.abc import Callable, Generator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Protocol

from nosolear.domain.jobs import JOB_PLANS, JobKind


@dataclass(frozen=True, slots=True)
class StepContext:
    job_id: str
    kind: JobKind
    attempt_id: str | None
    # A fraction 0..1 within this step; `run_job` persists (settled steps + fraction) / len(plan).
    progress: Callable[[float], None]


_current_job: ContextVar[str | None] = ContextVar("nosolear_current_job", default=None)


def current_job_id() -> str | None:
    """The job whose step is running in this context, or None. The metered layer reads it."""
    return _current_job.get()


@contextmanager
def running_job(job_id: str) -> Generator[None]:
    """Sets `current_job_id()` for the duration of one step's `run`."""
    token = _current_job.set(job_id)
    try:
        yield
    finally:
        _current_job.reset(token)


class Step(Protocol):
    name: str

    def applies(self, ctx: StepContext) -> bool:
        """False makes the step SKIPPED with message "not_applicable"."""
        ...

    def run(self, ctx: StepContext) -> None:
        """Idempotent: returns without a provider call when its stored analysis exists.

        Raises a `NosolearError` on failure. Any other exception becomes "internal_error".
        """
        ...


class StepRegistry:
    def __init__(self) -> None:
        self._steps: dict[tuple[JobKind, str], Step] = {}

    def register(self, kind: JobKind, step: Step) -> None:
        if step.name not in {spec.name for spec in JOB_PLANS[kind]}:
            raise ValueError(f"{step.name!r} is not a step of the {kind.value} plan")
        if (kind, step.name) in self._steps:
            raise ValueError(f"{step.name!r} is already registered for {kind.value}")
        self._steps[(kind, step.name)] = step

    def get(self, kind: JobKind, name: str) -> Step | None:
        return self._steps.get((kind, name))

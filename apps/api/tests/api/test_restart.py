from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest
from factories import FixedClock, loopback_client, make_settings
from fakes import FakeStep
from fastapi import FastAPI

from nosolear.api.app import create_app
from nosolear.api.deps import Services
from nosolear.app.steps import StepContext, StepRegistry
from nosolear.domain.budget import Provider, Unit
from nosolear.domain.jobs import JobKind, JobStatus

NOW = datetime(2026, 11, 13, 9, 0, tzinfo=UTC)
WAIT = 10.0  # every wait has a timeout: a regression fails the test rather than hanging it


class Crash(BaseException):
    """Stands in for the process dying mid-step. Nothing in the runner catches it, so the job row
    is left RUNNING with the crashed step recorded as running."""


def _crash(ctx: StepContext) -> None:
    raise Crash()


def _registry(*steps: FakeStep) -> StepRegistry:
    registry = StepRegistry()
    for step in steps:
        registry.register(JobKind.ANALYZE, step)
    return registry


def _services(app: FastAPI) -> Services:
    return cast(Services, app.state.services)


def test_restart_finishes_interrupted_job(tmp_path: Path) -> None:
    settings = make_settings(data_dir=tmp_path)
    score = FakeStep("score")  # DONE before the crash: must not run again
    crashing = FakeStep("transcribe", on_run=_crash)
    first = create_app(
        settings,
        step_registry=_registry(score, crashing),
        start_runner=False,
        clock=FixedClock(NOW),
    )
    with loopback_client(first) as client:
        services = _services(first)
        job = services.jobs.enqueue(JobKind.ANALYZE, None)
        with pytest.raises(Crash):
            services.runner.run_pending()
        interrupted = client.get(f"/api/jobs/{job.id}").json()
    assert interrupted["status"] == "running"
    assert interrupted["step"] == "transcribe"

    later = [FakeStep(name) for name in ("transcribe", "probe", "coach", "extract")]
    second = create_app(
        settings,
        step_registry=_registry(score, *later),
        start_runner=True,
        clock=FixedClock(NOW),
    )
    with loopback_client(second):
        services = _services(second)
        # no request is made: the startup recovery and the runner alone must finish the job
        assert services.runner.wait_idle(timeout=WAIT), "the restarted runner never went idle"
        finished = services.jobs.get(job.id)
    assert finished is not None
    assert finished.status is JobStatus.DONE
    assert len(score.runs) == 1, "a step recorded DONE before the crash ran again"
    assert all(len(step.runs) == 1 for step in later)


def test_restart_settles_orphaned_reservations(tmp_path: Path) -> None:
    settings = make_settings(data_dir=tmp_path)
    first = create_app(settings, start_runner=False, clock=FixedClock(NOW))
    with loopback_client(first):
        # a reservation with no settlement: what a crash mid-call leaves behind
        _services(first).ledger.reserve(Provider.ANTHROPIC, Unit.TOKENS, 500)

    second = create_app(settings, start_runner=False, clock=FixedClock(NOW))
    with loopback_client(second):
        usage = _services(second).ledger.usage(Provider.ANTHROPIC, Unit.TOKENS)
    assert usage.recorded == 500
    assert usage.reserved == 0

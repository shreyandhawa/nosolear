import logging
from datetime import UTC, datetime

import pytest
from factories import FixedClock
from fakes import FakeJobQueue, FakePaidPort, FakeStep, FakeUsageLedger

from nosolear.app.run_job import run_job
from nosolear.app.steps import StepContext, StepRegistry, current_job_id
from nosolear.budget.meter import Meter
from nosolear.domain.budget import Caps, Provider, Unit
from nosolear.domain.errors import (
    CapabilityMissing,
    CapExceeded,
    InvalidAudio,
    NosolearError,
    ProviderUnavailable,
)
from nosolear.domain.jobs import JobKind, JobStatus, StepRecord, StepState

T0 = datetime(2026, 11, 13, 9, 0, tzinfo=UTC)
ANALYZE = ["score", "transcribe", "probe", "coach", "extract"]
SETTLED = {StepState.DONE, StepState.SKIPPED, StepState.FAILED, StepState.BLOCKED}


def _queue() -> FakeJobQueue:
    return FakeJobQueue(FixedClock(T0))


def _registry(*steps: FakeStep, kind: JobKind = JobKind.ANALYZE) -> StepRegistry:
    registry = StepRegistry()
    for step in steps:
        registry.register(kind, step)
    return registry


def _by_name(steps: tuple[StepRecord, ...]) -> dict[str, StepRecord]:
    return {step.name: step for step in steps}


def _state_of(update_step: str | None, steps: tuple[StepRecord, ...]) -> StepState | None:
    return next((s.state for s in steps if s.name == update_step), None)


def test_runs_all_steps_in_plan_order_and_reports_progress() -> None:
    queue = _queue()
    job = queue.enqueue(JobKind.ANALYZE, None)
    order: list[str] = []
    steps = [FakeStep(name, on_run=lambda ctx, name=name: order.append(name)) for name in ANALYZE]
    finished = run_job(job_id=job.id, jobs=queue, registry=_registry(*steps))

    assert finished.status is JobStatus.DONE
    assert finished.progress == 1.0
    assert order == ANALYZE
    progress = [u.progress for u in queue.updates]
    assert progress == sorted(progress), "progress must never decrease"
    settled = [(u.step, u.progress) for u in queue.updates if _state_of(u.step, u.steps) in SETTLED]
    assert [p for _, p in settled] == [0.2, 0.4, 0.6, 0.8, 1.0]
    assert [name for name, _ in settled] == ANALYZE


def test_unregistered_steps_are_skipped_not_failed() -> None:
    queue = _queue()
    job = queue.enqueue(JobKind.ANALYZE, None)
    finished = run_job(job_id=job.id, jobs=queue, registry=StepRegistry())
    assert finished.status is JobStatus.DONE
    assert all((s.state, s.message) == (StepState.SKIPPED, "not_available") for s in finished.steps)


def test_not_applicable_step_is_skipped() -> None:
    queue = _queue()
    job = queue.enqueue(JobKind.ANALYZE, None)
    probe = FakeStep("probe", applies=False)
    finished = run_job(job_id=job.id, jobs=queue, registry=_registry(probe))
    assert probe.runs == []
    assert _by_name(finished.steps)["probe"] == StepRecord(
        "probe", StepState.SKIPPED, message="not_applicable"
    )
    assert finished.status is JobStatus.DONE


@pytest.mark.parametrize(
    "error",
    [
        pytest.param(InvalidAudio("empty"), id="invalid-audio"),
        pytest.param(CapExceeded(), id="cap-exceeded"),
        pytest.param(ProviderUnavailable(), id="provider-unavailable"),
        pytest.param(CapabilityMissing(), id="capability-missing"),
    ],
)
def test_typed_error_becomes_failed_step_with_safe_message(error: NosolearError) -> None:
    queue = _queue()
    job = queue.enqueue(JobKind.ANALYZE, None)
    finished = run_job(
        job_id=job.id, jobs=queue, registry=_registry(FakeStep("score", raises=error))
    )
    score = _by_name(finished.steps)["score"]
    assert score.state is StepState.FAILED
    assert score.error_code == error.code
    assert score.message == error.safe_message
    assert finished.status is JobStatus.FAILED


def test_unexpected_exception_is_internal_error_without_text(
    caplog: pytest.LogCaptureFixture,
) -> None:
    queue = _queue()
    job = queue.enqueue(JobKind.ANALYZE, None)
    planted = "sk-planted-secret"
    with caplog.at_level(logging.DEBUG):
        finished = run_job(
            job_id=job.id,
            jobs=queue,
            registry=_registry(FakeStep("score", raises=RuntimeError(planted))),
        )
    score = _by_name(finished.steps)["score"]
    assert score.error_code == "internal_error"
    assert score.message == "The step failed unexpectedly."
    assert planted not in repr(finished)
    assert planted not in repr(finished.steps)
    assert planted not in repr(queue.updates)
    assert planted not in caplog.text
    assert "RuntimeError" in caplog.text


def test_failed_step_does_not_stop_independent_steps() -> None:
    queue = _queue()
    job = queue.enqueue(JobKind.ANALYZE, None)
    steps = [FakeStep("score", raises=ProviderUnavailable())] + [
        FakeStep(name) for name in ANALYZE[1:]
    ]
    finished = run_job(job_id=job.id, jobs=queue, registry=_registry(*steps))
    assert all(step.runs for step in steps[1:])
    assert finished.status is JobStatus.FAILED


def test_dependent_step_is_blocked() -> None:
    queue = _queue()
    job = queue.enqueue(JobKind.ANALYZE, None)
    coach = FakeStep("coach")
    extract = FakeStep("extract")
    steps = [
        FakeStep("score"),
        FakeStep("transcribe", raises=ProviderUnavailable()),
        FakeStep("probe"),
        coach,
        extract,
    ]
    finished = run_job(job_id=job.id, jobs=queue, registry=_registry(*steps))
    by_name = _by_name(finished.steps)
    assert by_name["coach"] == StepRecord(
        "coach",
        StepState.BLOCKED,
        error_code="blocked",
        message="A step this one needs did not finish.",
    )
    assert coach.runs == []
    assert len(extract.runs) == 1
    assert finished.status is JobStatus.FAILED


def test_resumed_job_does_not_repeat_done_steps() -> None:
    queue = _queue()
    job = queue.enqueue(JobKind.ANALYZE, None)
    coach = FakeStep("coach", raises=ProviderUnavailable())
    score, transcribe, probe, extract = (
        FakeStep(n) for n in ("score", "transcribe", "probe", "extract")
    )
    registry = _registry(score, transcribe, probe, coach, extract)

    first = run_job(job_id=job.id, jobs=queue, registry=registry)
    assert first.status is JobStatus.FAILED

    queue.resume(job.id)
    coach.raises = None
    second = run_job(job_id=job.id, jobs=queue, registry=registry)

    assert second.status is JobStatus.DONE
    assert [len(s.runs) for s in (score, transcribe, probe)] == [1, 1, 1]
    assert [len(s.runs) for s in (coach, extract)] == [2, 2]


def test_cap_exceeded_step_fails_without_calling_provider() -> None:
    queue = _queue()
    job = queue.enqueue(JobKind.ANALYZE, None)
    clock = FixedClock(T0)
    ledger = FakeUsageLedger(
        Caps(azure_audio_seconds=10, azure_tts_chars=10, claude_tokens=10), clock
    )
    meter = Meter(ledger, job_id=current_job_id)
    port = FakePaidPort()

    def call_provider(ctx: StepContext) -> None:
        meter.call(Provider.AZURE, Unit.AUDIO_SECONDS, 100, lambda: port.run(1), actual=lambda n: n)

    finished = run_job(
        job_id=job.id,
        jobs=queue,
        registry=_registry(FakeStep("score", on_run=call_provider)),
    )
    score = _by_name(finished.steps)["score"]
    assert score.state is StepState.FAILED
    assert score.error_code == "cap_exceeded"
    assert port.calls == 0


def test_registry_rejects_unknown_or_duplicate_step_names() -> None:
    registry = StepRegistry()
    with pytest.raises(ValueError):
        registry.register(JobKind.RESCORE, FakeStep("score"))
    registry.register(JobKind.ANALYZE, FakeStep("score"))
    with pytest.raises(ValueError):
        registry.register(JobKind.ANALYZE, FakeStep("score"))
    assert registry.get(JobKind.ANALYZE, "score") is not None
    assert registry.get(JobKind.RESCORE, "score") is None


def test_step_progress_within_step_is_reported() -> None:
    queue = _queue()
    job = queue.enqueue(JobKind.RESCORE, None)
    extract = FakeStep("extract", on_run=lambda ctx: ctx.progress(0.5))
    finished = run_job(job_id=job.id, jobs=queue, registry=_registry(extract, kind=JobKind.RESCORE))
    progress = [u.progress for u in queue.updates]
    assert 0.5 in progress
    assert progress.index(0.5) < len(progress) - 1
    assert finished.progress == 1.0


def test_current_job_id_is_set_only_while_a_step_runs() -> None:
    queue = _queue()
    job = queue.enqueue(JobKind.RESCORE, None)
    seen: list[str | None] = []
    run_job(
        job_id=job.id,
        jobs=queue,
        registry=_registry(
            FakeStep("extract", on_run=lambda ctx: seen.append(current_job_id())),
            kind=JobKind.RESCORE,
        ),
    )
    assert seen == [job.id]
    assert current_job_id() is None

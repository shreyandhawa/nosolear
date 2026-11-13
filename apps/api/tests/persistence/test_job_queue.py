import json
import threading
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from factories import FixedClock
from fakes import FakeJobQueue
from sqlalchemy import Engine, text

from nosolear.domain.jobs import (
    JobKind,
    JobStatus,
    StepRecord,
    StepState,
    initial_steps,
)
from nosolear.persistence.job_queue import SqliteJobQueue, steps_from_json, steps_to_json
from nosolear.ports.jobs import JobNotResumable, JobQueue, UnknownJob

T0 = datetime(2026, 11, 12, 8, 0, tzinfo=UTC)
ANALYZE_NAMES = ["score", "transcribe", "probe", "coach", "extract"]


@pytest.fixture(params=["sqlite", "fake"])
def queue(request: pytest.FixtureRequest, db_engine: Engine) -> Iterator[JobQueue]:
    """The same assertions run against the SQLite queue and the in-memory fake."""
    clock = FixedClock(T0)
    if request.param == "sqlite":
        yield SqliteJobQueue(db_engine, clock=clock)
    else:
        yield FakeJobQueue(clock)


def _with(
    steps: tuple[StepRecord, ...], name: str, state: StepState, **extra: str
) -> tuple[StepRecord, ...]:
    return tuple(StepRecord(s.name, state, **extra) if s.name == name else s for s in steps)


def _initial() -> tuple[StepRecord, ...]:
    return initial_steps(JobKind.ANALYZE)


def test_enqueue_creates_queued_job_with_pending_steps(queue: JobQueue) -> None:
    job = queue.enqueue(JobKind.ANALYZE, None)
    assert job.status is JobStatus.QUEUED
    assert job.steps == _initial()
    assert (job.tries, job.progress, job.step, job.attempt_id) == (0, 0.0, None, None)
    assert queue.get(job.id) == job


def test_enqueue_rescore_has_no_attempt(queue: JobQueue) -> None:
    job = queue.enqueue(JobKind.RESCORE, None)
    assert job.kind is JobKind.RESCORE
    assert job.attempt_id is None
    assert [s.name for s in job.steps] == ["extract"]


def test_claim_next_is_fifo_and_marks_running(queue: JobQueue) -> None:
    first = queue.enqueue(JobKind.ANALYZE, None)
    second = queue.enqueue(JobKind.RESCORE, None)
    claimed_first = queue.claim_next()
    claimed_second = queue.claim_next()
    assert claimed_first is not None and claimed_second is not None
    assert (claimed_first.id, claimed_second.id) == (first.id, second.id)
    assert claimed_first.status is JobStatus.RUNNING
    assert claimed_first.tries == 1
    assert queue.claim_next() is None


def test_two_threads_never_claim_the_same_job(queue: JobQueue) -> None:
    ids = {queue.enqueue(JobKind.RESCORE, None).id for _ in range(20)}
    threads = 4
    barrier = threading.Barrier(threads)
    claimed: list[list[str]] = [[] for _ in range(threads)]

    def drain(slot: list[str]) -> None:
        barrier.wait()
        while (job := queue.claim_next()) is not None:
            slot.append(job.id)

    workers = [threading.Thread(target=drain, args=(claimed[i],)) for i in range(threads)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()
    everything = [job_id for slot in claimed for job_id in slot]
    assert len(everything) == 20
    assert set(everything) == ids


def test_update_persists_steps_progress_and_status(queue: JobQueue) -> None:
    job = queue.enqueue(JobKind.ANALYZE, None)
    queue.claim_next()
    steps = _with(_initial(), "score", StepState.DONE)
    steps = _with(steps, "transcribe", StepState.FAILED, error_code="invalid_audio", message="m")
    queue.update(job.id, steps=steps, step="transcribe", progress=0.4, status=JobStatus.FAILED)
    stored = queue.get(job.id)
    assert stored is not None
    assert (stored.steps, stored.step, stored.progress, stored.status) == (
        steps,
        "transcribe",
        0.4,
        JobStatus.FAILED,
    )
    queue.update(job.id, steps=steps, step="transcribe", progress=0.4)
    kept = queue.get(job.id)
    assert kept is not None and kept.status is JobStatus.FAILED


def test_update_unknown_job_raises_unknown_job(queue: JobQueue) -> None:
    with pytest.raises(UnknownJob):
        queue.update("nope", steps=_initial(), step=None, progress=0.0)


def test_steps_json_holds_only_safe_fields(db_engine: Engine) -> None:
    queue = SqliteJobQueue(db_engine, clock=FixedClock(T0))
    job = queue.enqueue(JobKind.ANALYZE, None)
    steps = _with(_initial(), "score", StepState.FAILED, error_code="invalid_audio", message="m")
    queue.update(job.id, steps=steps, step="score", progress=0.2)
    with db_engine.connect() as conn:
        raw = conn.execute(
            text("SELECT steps_json FROM jobs WHERE id = :id"), {"id": job.id}
        ).scalar_one()
    items = json.loads(raw)
    assert all(set(item) == {"name", "state", "error_code", "message"} for item in items)
    assert items[0] == {
        "name": "score",
        "state": "failed",
        "error_code": "invalid_audio",
        "message": "m",
    }


def test_steps_json_round_trips() -> None:
    steps = _with(_initial(), "coach", StepState.BLOCKED, error_code="blocked", message="x")
    assert steps_from_json(steps_to_json(steps)) == steps


def test_requeue_running_resets_running_steps(queue: JobQueue) -> None:
    running = queue.enqueue(JobKind.ANALYZE, None)
    queue.claim_next()
    steps = _with(_initial(), "score", StepState.DONE)
    steps = _with(steps, "transcribe", StepState.RUNNING)
    queue.update(running.id, steps=steps, step="transcribe", progress=0.2)

    failed = queue.enqueue(JobKind.RESCORE, None)
    queue.claim_next()
    queue.update(
        failed.id,
        steps=(StepRecord("extract", StepState.FAILED),),
        step="extract",
        progress=1.0,
        status=JobStatus.FAILED,
    )
    done = queue.enqueue(JobKind.RESCORE, None)
    queue.claim_next()
    queue.update(
        done.id,
        steps=(StepRecord("extract", StepState.DONE),),
        step="extract",
        progress=1.0,
        status=JobStatus.DONE,
    )
    before = (queue.get(failed.id), queue.get(done.id))

    assert queue.requeue_running() == 1
    got = queue.get(running.id)
    assert got is not None
    assert got.status is JobStatus.QUEUED
    assert got.tries == 1
    assert got.steps[0] == StepRecord("score", StepState.DONE)
    assert got.steps[1] == StepRecord("transcribe", StepState.PENDING)
    assert (queue.get(failed.id), queue.get(done.id)) == before


def test_resume_failed_job_requeues_with_reset_steps(queue: JobQueue) -> None:
    job = queue.enqueue(JobKind.ANALYZE, None)
    queue.claim_next()
    steps = (
        StepRecord("score", StepState.DONE),
        StepRecord("transcribe", StepState.DONE),
        StepRecord("probe", StepState.DONE),
        StepRecord("coach", StepState.FAILED, error_code="provider_unavailable", message="m"),
        StepRecord("extract", StepState.DONE),
    )
    queue.update(job.id, steps=steps, step="coach", progress=0.8, status=JobStatus.FAILED)

    resumed = queue.resume(job.id)
    assert resumed.status is JobStatus.QUEUED
    assert resumed.tries == 1
    assert [(s.name, s.state) for s in resumed.steps] == [
        ("score", StepState.DONE),
        ("transcribe", StepState.DONE),
        ("probe", StepState.DONE),
        ("coach", StepState.PENDING),
        ("extract", StepState.PENDING),
    ]
    assert queue.get(job.id) == resumed
    claimed = queue.claim_next()
    assert claimed is not None and claimed.id == job.id


def test_resume_non_failed_job_raises_job_not_resumable(queue: JobQueue) -> None:
    job = queue.enqueue(JobKind.ANALYZE, None)
    with pytest.raises(JobNotResumable):
        queue.resume(job.id)


def test_resume_unknown_job_raises_unknown_job(queue: JobQueue) -> None:
    with pytest.raises(UnknownJob):
        queue.resume("nope")


def test_get_unknown_returns_none(queue: JobQueue) -> None:
    assert queue.get("nope") is None

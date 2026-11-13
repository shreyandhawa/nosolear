import threading
from datetime import UTC, datetime

from factories import FixedClock
from fakes import FakeJobQueue

from nosolear.adapters.thread_pool_runner import ThreadPoolJobRunner
from nosolear.domain.jobs import JobKind

T0 = datetime(2026, 11, 13, 9, 0, tzinfo=UTC)
WAIT = 10.0  # every event wait in this module has a timeout, so a bug fails instead of hanging
RUNNER_THREAD_PREFIX = "nosolear-job-"


class Recorder:
    """A `run` callable that records each job id and the thread it ran on."""

    def __init__(self, *, raise_on: str | None = None) -> None:
        self.calls: list[str] = []
        self.threads: list[int] = []
        self.raise_on = raise_on
        self._lock = threading.Lock()

    def __call__(self, job_id: str) -> None:
        with self._lock:
            self.calls.append(job_id)
            self.threads.append(threading.get_ident())
        if job_id == self.raise_on:
            raise RuntimeError("planted failure inside run")


def _queue() -> FakeJobQueue:
    return FakeJobQueue(FixedClock(T0))


def _enqueue(queue: FakeJobQueue, count: int) -> list[str]:
    return [queue.enqueue(JobKind.ANALYZE, None).id for _ in range(count)]


def _runner_threads_alive() -> list[threading.Thread]:
    return [
        t for t in threading.enumerate() if t.name.startswith(RUNNER_THREAD_PREFIX) and t.is_alive()
    ]


def test_runs_queued_jobs_to_completion() -> None:
    queue = _queue()
    ids = _enqueue(queue, 3)
    recorder = Recorder()
    runner = ThreadPoolJobRunner(queue, recorder, workers=1, poll_seconds=0.05)
    try:
        runner.start()
        runner.wake()
        assert runner.wait_idle(timeout=WAIT)
    finally:
        runner.stop(timeout=WAIT)
    assert sorted(recorder.calls) == sorted(ids)


def test_worker_survives_a_raising_run() -> None:
    queue = _queue()
    first, second = _enqueue(queue, 2)
    recorder = Recorder(raise_on=first)
    runner = ThreadPoolJobRunner(queue, recorder, workers=1, poll_seconds=0.05)
    try:
        runner.start()
        runner.wake()
        assert runner.wait_idle(timeout=WAIT)
    finally:
        runner.stop(timeout=WAIT)
    assert recorder.calls == [first, second]


def test_stop_joins_workers() -> None:
    runner = ThreadPoolJobRunner(_queue(), Recorder(), workers=2, poll_seconds=0.05)
    runner.start()
    assert len(_runner_threads_alive()) == 2
    runner.stop(timeout=WAIT)
    assert _runner_threads_alive() == []


def test_jobs_enqueued_after_start_are_picked_up_within_poll_interval() -> None:
    queue = _queue()
    seen = threading.Event()
    ids: list[str] = []

    def run(job_id: str) -> None:
        ids.append(job_id)
        seen.set()

    runner = ThreadPoolJobRunner(queue, run, workers=1, poll_seconds=0.05)
    try:
        runner.start()
        (job_id,) = _enqueue(queue, 1)  # no wake(): the poll alone must find it
        assert seen.wait(WAIT), "the idle worker never polled the queue"
    finally:
        runner.stop(timeout=WAIT)
    assert ids == [job_id]


def test_run_pending_runs_every_queued_job_in_the_calling_thread() -> None:
    queue = _queue()
    ids = _enqueue(queue, 3)
    recorder = Recorder()
    runner = ThreadPoolJobRunner(queue, recorder, workers=1)

    assert runner.run_pending() == 3
    assert recorder.calls == ids
    assert set(recorder.threads) == {threading.get_ident()}
    assert runner.run_pending() == 0


def test_wait_idle_is_false_while_a_job_is_still_running() -> None:
    queue = _queue()
    _enqueue(queue, 1)
    release = threading.Event()
    started = threading.Event()

    def blocking_run(job_id: str) -> None:
        started.set()
        release.wait(WAIT)

    runner = ThreadPoolJobRunner(queue, blocking_run, workers=1, poll_seconds=0.05)
    try:
        runner.start()
        assert started.wait(WAIT)
        assert runner.wait_idle(timeout=0.2) is False
        release.set()
        assert runner.wait_idle(timeout=WAIT) is True
    finally:
        release.set()
        runner.stop(timeout=WAIT)

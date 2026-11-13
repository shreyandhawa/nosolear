"""Runs queued jobs on a fixed pool of daemon threads (ARCHITECTURE.md section 13, Phase 0c).

A worker claims a job under the runner's lock, so `busy` and the empty-claim count are read
consistently: an empty claim made while nothing is busy proves the queue was empty at that moment.
A raising `run` is logged by exception type only and never kills its worker.
"""

import logging
import threading
import time
from collections.abc import Callable

from nosolear.domain.jobs import Job
from nosolear.ports.jobs import JobQueue

logger = logging.getLogger(__name__)

THREAD_NAME_PREFIX = "nosolear-job-"


class ThreadPoolJobRunner:
    def __init__(
        self,
        jobs: JobQueue,
        run: Callable[[str], object],
        *,
        workers: int,
        poll_seconds: float = 0.5,
    ) -> None:
        if workers < 1:
            raise ValueError("a runner needs at least one worker")
        self._jobs = jobs
        self._run = run
        self._workers = workers
        self._poll_seconds = poll_seconds
        self._cond = threading.Condition()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        self._busy = 0  # jobs claimed and not yet finished; guarded by `_cond`
        self._empty_claims = 0  # claims that found no queued job; guarded by `_cond`

    def start(self) -> None:
        if self._threads:
            raise RuntimeError("the runner is already started")
        self._stop.clear()
        for index in range(self._workers):
            thread = threading.Thread(
                target=self._worker, name=f"{THREAD_NAME_PREFIX}{index}", daemon=True
            )
            self._threads.append(thread)
            thread.start()

    def wake(self) -> None:
        self._wake.set()

    def run_pending(self) -> int:
        """Runs queued jobs in the calling thread until none is queued. Returns how many ran."""
        ran = 0
        while (job := self._claim()) is not None:
            self._execute(job)
            ran += 1
        return ran

    def wait_idle(self, timeout: float = 10.0) -> bool:
        """True once a claim has found the queue empty and no job is running."""
        deadline = time.monotonic() + timeout
        with self._cond:
            start = self._empty_claims
            self._wake.set()
            while not (self._empty_claims > start and self._busy == 0):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._cond.wait(remaining)
            return True

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        self._wake.set()
        for thread in self._threads:
            thread.join(timeout)
        self._threads = []

    def _worker(self) -> None:
        while not self._stop.is_set():
            job = self._claim()
            if job is not None:
                self._execute(job)
                continue
            self._wake.wait(self._poll_seconds)
            # cleared before the next claim, so a wake that arrives during the claim is not lost
            self._wake.clear()

    def _claim(self) -> Job | None:
        with self._cond:
            job = self._jobs.claim_next()
            if job is None:
                self._empty_claims += 1
                self._cond.notify_all()
            else:
                self._busy += 1
            return job

    def _execute(self, job: Job) -> None:
        try:
            self._run(job.id)
        except Exception as error:
            # Only the exception type: its message may carry input bytes or a key.
            logger.error("job run failed: %s", type(error).__name__)
        finally:
            with self._cond:
                self._busy -= 1
                self._cond.notify_all()

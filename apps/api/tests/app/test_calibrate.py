"""The calibration session end to end: use cases, the job steps and the calibrated config."""

import threading
from collections.abc import Callable
from typing import Any

import pytest
from calibration_fixtures import small_content
from factories import NEUTRAL, count
from harness import Harness
from sqlalchemy import Engine, select

from nosolear.app import calibrate_job
from nosolear.app.calibrate import (
    CalibrationNotRunning,
    NothingRecorded,
    NothingToCalibrate,
    TokensPending,
    calibration_view,
    finish_calibration,
    skip_calibration,
    start_calibration,
)
from nosolear.domain.errors import CapExceeded
from nosolear.domain.scoring import ConfigKind
from nosolear.domain.taxonomy import DEFAULT_TAXONOMY as TAX
from nosolear.domain.taxonomy import Detector
from nosolear.persistence.calibration_repository import CalibrationRepository
from nosolear.persistence.models import calibration_runs, jobs
from nosolear.persistence.scoring_repository import ScoringConfigRepository
from nosolear.ports.calibration_store import CalibrationRunRecord
from nosolear.ports.clock import Clock

AZURE = frozenset({Detector.AZURE_PA})


def parts(h: Harness) -> tuple[Any, CalibrationRepository]:
    services: Any = h.client.app.state.services  # pyright: ignore[reportAttributeAccessIssue]
    return services, CalibrationRepository(h.engine, h.clock)


def start(h: Harness, available: frozenset[Detector] = AZURE) -> Any:
    _, store = parts(h)
    return start_calibration(
        store=store,
        content=small_content(),
        pack=NEUTRAL,
        available=available,
        taxonomy=TAX,
        clock=h.clock,
    )


def finish(h: Harness) -> str:
    services, store = parts(h)
    return finish_calibration(store=store, queue=services.jobs)


def jobs_of_kind(h: Harness, kind: str) -> list[str]:
    with h.engine.connect() as conn:
        rows = conn.execute(select(jobs.c.status).where(jobs.c.kind == kind)).all()
    return [str(r.status) for r in rows]


def uploads_standing_in(h: Harness, view: Any) -> None:
    for item in view.items:
        h.upload(item.attempt_id, item.stand_in_text)
    h.drain()


def test_start_creates_session_attempts_and_trials(make_harness: Callable[..., Harness]):
    h = make_harness(content=small_content())
    view = start(h)
    assert len(view.items) == 2 * 5 * 3
    assert count(h.engine, "calibration_trials") == 30
    instructions = {i.instruction for i in view.items if i.word == "vest"}
    assert 'Say "vest" as correctly as possible, in General American.' in instructions


def test_start_returns_the_open_run(make_harness: Callable[..., Harness]):
    h = make_harness(content=small_content())
    first = start(h)
    second = start(h)
    assert second.run.id == first.run.id
    assert count(h.engine, "attempts") == 30


def test_start_with_no_detectors_raises(make_harness: Callable[..., Harness]):
    h = make_harness(content=small_content())
    with pytest.raises(NothingToCalibrate):
        start(h, available=frozenset())


def test_skip_without_a_run_records_a_skipped_run(make_harness: Callable[..., Harness]):
    h = make_harness(content=small_content())
    _, store = parts(h)
    view = skip_calibration(store=store, clock=h.clock)
    assert view.run.status == "skipped" and view.run.session_id is None


def test_skip_marks_the_open_run_skipped(make_harness: Callable[..., Harness]):
    h = make_harness(content=small_content())
    run_id = start(h).run.id
    _, store = parts(h)
    assert skip_calibration(store=store, clock=h.clock).run.id == run_id
    latest = store.latest()
    assert latest is not None and latest.status == "skipped"


def test_finish_requires_settled_tokens(make_harness: Callable[..., Harness]):
    h = make_harness(content=small_content())
    view = start(h)
    h.upload(view.items[0].attempt_id, view.items[0].stand_in_text)
    with pytest.raises(TokensPending):
        finish(h)


def test_finish_needs_a_recording(make_harness: Callable[..., Harness]):
    h = make_harness(content=small_content())
    start(h)
    with pytest.raises(NothingRecorded):
        finish(h)


def test_finish_without_a_run_is_refused(make_harness: Callable[..., Harness]):
    h = make_harness(content=small_content())
    with pytest.raises(CalibrationNotRunning):
        finish(h)


def test_finish_runs_controls_evaluates_and_queues_rescore(
    make_harness: Callable[..., Harness],
):
    h = make_harness(content=small_content())
    uploads_standing_in(h, start(h))
    finish(h)
    h.drain()
    _, store = parts(h)
    run = store.latest()
    assert run is not None and run.status == "done" and run.scoring_config_id is not None
    cfg = ScoringConfigRepository(h.engine, TAX).newest()
    assert cfg.kind is ConfigKind.CALIBRATED
    assert {(k.error_key, k.enabled) for k in cfg.key_rules} == {
        ("sound.sub.f.p", True),
        ("sound.sub.v.w", True),
    }
    assert jobs_of_kind(h, "rescore") == ["done"]


def test_controls_are_scored_once_per_word_across_a_resumed_job(
    make_harness: Callable[..., Harness], monkeypatch: pytest.MonkeyPatch
):
    h = make_harness(content=small_content())
    uploads_standing_in(h, start(h))
    real = calibrate_job.evaluate
    calls: list[int] = []

    def flaky(*args: Any, **kwargs: Any) -> Any:
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("evaluation failed once")
        return real(*args, **kwargs)

    monkeypatch.setattr(calibrate_job, "evaluate", flaky)
    h.voice.calls.clear()
    job_id = finish(h)
    h.drain()
    services: Any = h.client.app.state.services  # pyright: ignore[reportAttributeAccessIssue]
    assert services.jobs.get(job_id).status.value == "failed"
    services.jobs.resume(job_id)
    h.drain()
    assert h.voice.calls["scorer"] == 10
    _, store = parts(h)
    latest = store.latest()
    assert latest is not None and latest.status == "done"


def test_cap_exceeded_during_controls_keeps_run_running(
    make_harness: Callable[..., Harness],
):
    h = make_harness(content=small_content())
    uploads_standing_in(h, start(h))
    h.voice.fail_all(CapExceeded())
    job_id = finish(h)
    h.drain()
    services: Any = h.client.app.state.services  # pyright: ignore[reportAttributeAccessIssue]
    assert services.jobs.get(job_id).status.value == "failed"
    _, store = parts(h)
    latest = store.latest()
    assert latest is not None and latest.status == "running"
    assert count(h.engine, "scoring_configs") == 1  # only the v0 row


def test_correct_take_flags_warn_but_do_not_disable(make_harness: Callable[..., Harness]):
    h = make_harness(content=small_content())
    view = start(h)
    standing_in = {"vest": "west", "van": "wan"}
    for item in view.items:
        text = (
            standing_in[item.word]
            if not item.deliberate and item.word in standing_in
            else item.stand_in_text
        )
        h.upload(item.attempt_id, text)
    h.drain()
    finish(h)
    h.drain()
    _, store = parts(h)
    view = calibration_view(store=store, content=small_content())
    assert view is not None
    result = next(r for r in view.results if r.error_key == "sound.sub.v.w")
    assert result.enabled
    assert result.warning is not None and result.warning.startswith(
        "Your own correct takes were flagged 40% of the time (TTS controls: 0%)."
    )


def test_finish_twice_returns_the_same_job(make_harness: Callable[..., Harness]):
    h = make_harness(content=small_content())
    view = start(h)
    h.upload(view.items[0].attempt_id, view.items[0].stand_in_text)
    h.drain()
    assert finish(h) == finish(h)


def test_a_done_run_can_be_started_again(make_harness: Callable[..., Harness]):
    h = make_harness(content=small_content())
    uploads_standing_in(h, start(h))
    finish(h)
    h.drain()
    again = start(h)
    assert again.run.status == "running"
    assert again.run.session_id is not None
    assert len(again.items) == 30


def test_no_run_gives_no_view(make_harness: Callable[..., Harness]):
    h = make_harness(content=small_content())
    _, store = parts(h)
    assert calibration_view(store=store, content=small_content()) is None


class _GatedStore(CalibrationRepository):
    """Holds each thread at its first `running()` until both threads have read it, so both see
    no open run and both reach `start`. Later reads pass straight through."""

    def __init__(self, engine: Engine, clock: Clock, gate: threading.Barrier) -> None:
        super().__init__(engine, clock)
        self._gate = gate
        self._local = threading.local()

    def running(self) -> CalibrationRunRecord | None:
        found = super().running()
        if not getattr(self._local, "passed", False):
            self._local.passed = True
            self._gate.wait()
        return found


def test_concurrent_starts_both_return_the_one_open_run(make_harness: Callable[..., Harness]):
    h = make_harness(content=small_content())
    gate = threading.Barrier(2)
    results: list[object] = []
    failures: list[BaseException] = []
    lock = threading.Lock()

    def start_once() -> None:
        store = _GatedStore(h.engine, h.clock, gate)
        try:
            view = start_calibration(
                store=store,
                content=small_content(),
                pack=NEUTRAL,
                available=AZURE,
                taxonomy=TAX,
                clock=h.clock,
            )
        except BaseException as exc:
            with lock:
                failures.append(exc)
        else:
            with lock:
                results.append(view)

    threads = [threading.Thread(target=start_once) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert failures == [], "a losing start must return the open run, not raise"
    assert len(results) == 2
    run_ids = {view.run.id for view in results}  # pyright: ignore[reportAttributeAccessIssue]
    assert len(run_ids) == 1
    with h.engine.connect() as conn:
        runs = conn.execute(select(calibration_runs.c.id)).all()
    assert len(runs) == 1, "the race must not write a second run"

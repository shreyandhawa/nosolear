"""The calibration session's use cases (ARCHITECTURE.md section 9.2). Each takes its ports as
arguments, so the routes and the CLI wire the same code. Nothing here calls a provider: the
paid calls happen in the calibrate job's controls step, after the user has recorded the takes."""

from dataclasses import dataclass
from uuid import uuid4

from nosolear.domain.calibration import (
    CalibrationPlan,
    PairResult,
    evaluate,
    plan_calibration,
)
from nosolear.domain.calibration_items import calibration_instruction
from nosolear.domain.content import SeedContent, calibration_word, stand_in_text
from nosolear.domain.jobs import JobKind
from nosolear.domain.packs import LanguagePack
from nosolear.domain.taxonomy import Detector, Taxonomy
from nosolear.ports.calibration_store import CalibrationRunRecord, CalibrationStore, RunAlreadyOpen
from nosolear.ports.clock import Clock
from nosolear.ports.jobs import JobQueue


class CalibrationError(ValueError):
    """A refused step. `message` is a literal sentence the API and the CLI may show."""

    code: str = "calibration_error"
    message: str = "The calibration step was refused."

    def __init__(self) -> None:
        super().__init__(self.message)


class NothingToCalibrate(CalibrationError):
    code = "nothing_to_calibrate"
    message = (
        "No detector can be calibrated on this install: run nosolear doctor --probe, "
        "or skip calibration."
    )


class CalibrationNotRunning(CalibrationError):
    code = "calibration_not_running"
    message = "No calibration run is in progress."


class NothingRecorded(CalibrationError):
    code = "nothing_recorded"
    message = "Record at least one calibration word before finishing."


class TokensPending(CalibrationError):
    code = "tokens_pending"
    message = (
        "Some calibration recordings are still being analyzed. Try again when their jobs finish."
    )


@dataclass(frozen=True, slots=True)
class CalibrationItemView:
    attempt_id: str
    order: int
    error_key: str
    word: str
    deliberate: bool
    take: int
    instruction: str
    stand_in_text: str
    recorded: bool
    job_status: str | None


@dataclass(frozen=True, slots=True)
class CalibrationView:
    run: CalibrationRunRecord
    items: tuple[CalibrationItemView, ...]
    results: tuple[PairResult, ...]


def _view_items(
    store: CalibrationStore, run_id: str, content: SeedContent | None
) -> tuple[CalibrationItemView, ...]:
    takes = content.calibration_set.takes_per_word if content is not None else 2
    out: list[CalibrationItemView] = []
    for item in store.items(run_id):
        word = content.calibration_set.word(item.item_id) if content is not None else None
        if word is None:
            word = calibration_word(item.error_key, item.word, item.word, "")
        instruction = calibration_instruction(
            word, deliberate=item.deliberate, take=item.take, takes=takes
        )
        out.append(
            CalibrationItemView(
                attempt_id=item.attempt_id,
                order=item.order,
                error_key=item.error_key,
                word=item.word,
                deliberate=item.deliberate,
                take=item.take,
                instruction=instruction,
                stand_in_text=stand_in_text(word, deliberate=item.deliberate),
                recorded=item.recorded,
                job_status=item.job_status,
            )
        )
    return tuple(out)


def _view(
    store: CalibrationStore, run: CalibrationRunRecord, content: SeedContent | None
) -> CalibrationView:
    results: tuple[PairResult, ...] = ()
    if run.status == "done":
        results = evaluate(record.trial for record in store.trials(run.id))
    return CalibrationView(run=run, items=_view_items(store, run.id, content), results=results)


def start_calibration(
    *,
    store: CalibrationStore,
    content: SeedContent,
    pack: LanguagePack,
    available: frozenset[Detector],
    taxonomy: Taxonomy,
    clock: Clock,
) -> CalibrationView:
    """Starts a run, or returns the one already open. Raises `NothingToCalibrate` when no
    detector is available for any key."""
    open_run = store.running()
    if open_run is not None:
        return _view(store, open_run, content)
    plan: CalibrationPlan = plan_calibration(
        content.calibration_set,
        emphasis=pack.calibration_emphasis,
        available=available,
        taxonomy=taxonomy,
    )
    if not plan.tokens:
        raise NothingToCalibrate()
    try:
        run = store.start(
            run_id=uuid4().hex,
            session_id=uuid4().hex,
            plan=plan,
            now=clock.now(),
        )
    except RunAlreadyOpen:
        # A concurrent start won the race between the check above and the insert. Return the
        # run it opened, as a start with a run already open always does.
        raced = store.running()
        if raced is None:
            raise
        return _view(store, raced, content)
    return _view(store, run, content)


def skip_calibration(*, store: CalibrationStore, clock: Clock) -> CalibrationView:
    run = store.skip(run_id=uuid4().hex, now=clock.now())
    return CalibrationView(run=run, items=(), results=())


def finish_calibration(*, store: CalibrationStore, queue: JobQueue) -> str:
    """Queues the calibrate job and returns its id. Returns the open job's id when one exists, so
    a second call never queues a second job. Controls are paid, so they run only after every
    recording has been analyzed."""
    open_job = store.open_calibrate_job()
    if open_job is not None:
        return open_job
    run = store.running()
    if run is None:
        raise CalibrationNotRunning()
    items = store.items(run.id)
    recorded = [item for item in items if item.recorded]
    if not recorded:
        raise NothingRecorded()
    if any(item.job_status in ("queued", "running") for item in recorded):
        raise TokensPending()
    # The job names one of this run's attempts, so its steps act on this run and no other.
    return queue.enqueue(JobKind.CALIBRATE, recorded[0].attempt_id).id


def calibration_view(
    *, store: CalibrationStore, content: SeedContent | None
) -> CalibrationView | None:
    run = store.latest()
    if run is None:
        return None
    return _view(store, run, content)

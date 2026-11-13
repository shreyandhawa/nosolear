"""`/api/calibration`: the calibration session. Every paid call happens later, in the calibrate
job, so these routes only record takes and queue work. Refusals are 409 `ErrorOut` bodies with
the safe sentences from `app/calibrate.py`."""

from typing import Annotated

from fastapi import APIRouter, Depends

from nosolear.api.calibration_schemas import (
    CalibrationItemOut,
    CalibrationResultOut,
    CalibrationRunOut,
)
from nosolear.api.deps import (
    Services,
    get_available_detectors,
    get_calibration_store,
    get_clock,
    get_seed_content,
    get_services,
    get_settings,
    load_active_pack,
)
from nosolear.api.errors import ApiError
from nosolear.api.schemas import JobAcceptedOut
from nosolear.app.calibrate import (
    CalibrationError,
    CalibrationView,
    calibration_view,
    finish_calibration,
    skip_calibration,
    start_calibration,
)
from nosolear.domain.content import SeedContent
from nosolear.domain.packs import PackError
from nosolear.domain.taxonomy import DEFAULT_TAXONOMY, Detector
from nosolear.ports.calibration_store import CalibrationStore
from nosolear.ports.clock import Clock
from nosolear.settings import Settings

router = APIRouter()


def _refused(error: CalibrationError) -> ApiError:
    return ApiError(409, error.code, error.message)


def _content(content: SeedContent | None) -> SeedContent:
    if content is None:
        raise ApiError(409, "content_unavailable", "The calibration content could not be loaded.")
    return content


def _run_out(view: CalibrationView) -> CalibrationRunOut:
    run = view.run
    return CalibrationRunOut(
        run_id=run.id,
        session_id=run.session_id,
        status=run.status,
        scoring_config_id=run.scoring_config_id,
        started_at=run.started_at,
        completed_at=run.completed_at,
        items=[
            CalibrationItemOut(
                attempt_id=i.attempt_id,
                order=i.order,
                error_key=i.error_key,
                word=i.word,
                deliberate=i.deliberate,
                take=i.take,
                instruction=i.instruction,
                stand_in_text=i.stand_in_text,
                recorded=i.recorded,
                job_status=i.job_status,
            )
            for i in view.items
        ],
        results=[
            CalibrationResultOut(
                detector=r.detector.value,
                error_key=r.error_key,
                errors=r.counts.errors,
                hits=r.counts.hits,
                controls=r.counts.controls,
                false_alarms=r.counts.false_alarms,
                correct_takes=r.counts.correct_takes,
                correct_flags=r.counts.correct_flags,
                covered=r.covered,
                enabled=r.enabled,
                hit_rate=r.hit_rate,
                false_alarm_rate=r.false_alarm_rate,
                correct_take_flag_rate=r.correct_take_flag_rate,
                warning=r.warning,
            )
            for r in view.results
        ],
    )


@router.post("/api/calibration", operation_id="startCalibration")
def start_route(
    store: Annotated[CalibrationStore, Depends(get_calibration_store)],
    content: Annotated[SeedContent | None, Depends(get_seed_content)],
    settings: Annotated[Settings, Depends(get_settings)],
    available: Annotated[frozenset[Detector], Depends(get_available_detectors)],
    clock: Annotated[Clock, Depends(get_clock)],
) -> CalibrationRunOut:
    seed = _content(content)
    try:
        pack = load_active_pack(settings)
    except PackError:
        raise ApiError(409, "pack_unavailable", "The language pack could not be loaded.") from None
    try:
        view = start_calibration(
            store=store,
            content=seed,
            pack=pack,
            available=available,
            taxonomy=DEFAULT_TAXONOMY,
            clock=clock,
        )
    except CalibrationError as error:
        raise _refused(error) from None
    return _run_out(view)


@router.get("/api/calibration", operation_id="getCalibration")
def get_route(
    store: Annotated[CalibrationStore, Depends(get_calibration_store)],
    content: Annotated[SeedContent | None, Depends(get_seed_content)],
) -> CalibrationRunOut:
    view = calibration_view(store=store, content=_content(content))
    if view is None:
        raise ApiError(404, "no_calibration", "No calibration run exists yet.")
    return _run_out(view)


@router.post("/api/calibration/skip", operation_id="skipCalibration")
def skip_route(
    store: Annotated[CalibrationStore, Depends(get_calibration_store)],
    clock: Annotated[Clock, Depends(get_clock)],
) -> CalibrationRunOut:
    return _run_out(skip_calibration(store=store, clock=clock))


@router.post("/api/calibration/finish", operation_id="finishCalibration", status_code=202)
def finish_route(
    store: Annotated[CalibrationStore, Depends(get_calibration_store)],
    services: Annotated[Services, Depends(get_services)],
) -> JobAcceptedOut:
    try:
        job_id = finish_calibration(store=store, queue=services.jobs)
    except CalibrationError as error:
        raise _refused(error) from None
    services.runner.wake()
    return JobAcceptedOut(job_id=job_id)

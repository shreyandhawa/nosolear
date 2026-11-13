"""`/api/baseline`: the baseline session. Recording and analysis happen through the attempt
routes and the analyze jobs; these routes start, read and complete the session, and read its
report. Refusals are 409 `ErrorOut` bodies with the safe sentences from `app/baseline.py`."""

from typing import Annotated

from fastapi import APIRouter, Depends

from nosolear.api.baseline_schemas import (
    BaselineItemOut,
    BaselineReportOut,
    BaselineSessionOut,
    ClipOut,
    ReportItemOut,
    SkillScoreOut,
)
from nosolear.api.deps import (
    get_baseline_store,
    get_calibration_store,
    get_clock,
    get_extraction_inputs,
    get_observation_repository,
    get_profile_repository,
    get_scoring_configs,
    get_seed_content,
    get_settings,
    load_active_pack,
)
from nosolear.api.errors import ApiError
from nosolear.app.baseline import (
    BaselineError,
    BaselineView,
    baseline_report,
    baseline_view,
    complete_baseline,
    start_baseline,
)
from nosolear.domain.baseline_report import BaselineReport
from nosolear.domain.content import SeedContent
from nosolear.domain.packs import PackError
from nosolear.domain.taxonomy import DEFAULT_TAXONOMY
from nosolear.ports.baseline_store import BaselineProfileStore, BaselineStore
from nosolear.ports.calibration_store import CalibrationStore
from nosolear.ports.clock import Clock
from nosolear.ports.scoring_stores import ExtractionInputs, ScoringConfigReader
from nosolear.ports.stores import ObservationReader
from nosolear.settings import Settings

router = APIRouter()


def _content(content: SeedContent | None) -> SeedContent:
    if content is None:
        raise ApiError(409, "content_unavailable", "The baseline content could not be loaded.")
    return content


def _session_out(view: BaselineView) -> BaselineSessionOut:
    session = view.session
    return BaselineSessionOut(
        session_id=session.id,
        protocol_version=session.protocol_version,
        started_at=session.started_at,
        completed_at=session.completed_at,
        items=[
            BaselineItemOut(
                attempt_id=i.attempt_id,
                order=i.order,
                section=i.section,
                step=i.step,
                text=i.text,
                scripted=i.scripted,
                max_seconds=i.max_seconds,
                start_limit_seconds=i.start_limit_seconds,
                stand_in_text=i.stand_in_text,
                recorded=i.recorded,
                job_status=i.job_status,
            )
            for i in view.items
        ],
    )


def _report_out(report: BaselineReport) -> BaselineReportOut:
    return BaselineReportOut(
        session_id=report.session_id,
        completed_at=report.completed_at,
        calibration=report.calibration.value,
        scoring_config_id=report.scoring_config_id,
        snapshot_id=report.snapshot_id,
        items=[
            ReportItemOut(
                error_key=i.error_key,
                description=i.description,
                skill=i.skill.value,
                impact=i.impact,
                p_hat=i.p_hat,
                ci_low=i.ci_low,
                ci_high=i.ci_high,
                n_eff=i.n_eff,
                status=i.status.value,
                priority=i.priority,
                provisional=i.provisional,
                clips=[
                    ClipOut(
                        attempt_id=c.attempt_id,
                        start_ms=c.start_ms,
                        end_ms=c.end_ms,
                        word=c.word,
                        expected=c.expected,
                        produced=c.produced,
                    )
                    for c in i.clips
                ],
            )
            for i in report.items
        ],
        skill_scores=[
            SkillScoreOut(
                skill=s.skill.value,
                score=s.score,
                values=dict(s.values),
                scores=dict(s.scores),
            )
            for s in report.skill_scores
        ],
        notes=list(report.notes),
    )


@router.post("/api/baseline", operation_id="startBaseline")
def start_route(
    store: Annotated[BaselineStore, Depends(get_baseline_store)],
    content: Annotated[SeedContent | None, Depends(get_seed_content)],
    clock: Annotated[Clock, Depends(get_clock)],
) -> BaselineSessionOut:
    seed = _content(content)
    return _session_out(start_baseline(store=store, content=seed, clock=clock))


@router.get("/api/baseline", operation_id="getBaseline")
def get_route(
    store: Annotated[BaselineStore, Depends(get_baseline_store)],
    content: Annotated[SeedContent | None, Depends(get_seed_content)],
) -> BaselineSessionOut:
    view = baseline_view(store=store, content=_content(content))
    if view is None:
        raise ApiError(404, "no_baseline", "No baseline exists yet.")
    return _session_out(view)


@router.post("/api/baseline/complete", operation_id="completeBaseline")
def complete_route(
    store: Annotated[BaselineStore, Depends(get_baseline_store)],
    content: Annotated[SeedContent | None, Depends(get_seed_content)],
    settings: Annotated[Settings, Depends(get_settings)],
    inputs: Annotated[ExtractionInputs, Depends(get_extraction_inputs)],
    observations: Annotated[ObservationReader, Depends(get_observation_repository)],
    profiles: Annotated[BaselineProfileStore, Depends(get_profile_repository)],
    configs: Annotated[ScoringConfigReader, Depends(get_scoring_configs)],
    calibration: Annotated[CalibrationStore, Depends(get_calibration_store)],
    clock: Annotated[Clock, Depends(get_clock)],
) -> BaselineReportOut:
    seed = _content(content)
    try:
        pack = load_active_pack(settings)
    except PackError:
        raise ApiError(409, "pack_unavailable", "The language pack could not be loaded.") from None
    try:
        report = complete_baseline(
            store=store,
            content=seed,
            inputs=inputs,
            observations=observations,
            profiles=profiles,
            configs=configs,
            calibration=calibration,
            taxonomy=DEFAULT_TAXONOMY,
            pack=pack,
            clock=clock,
        )
    except BaselineError as error:
        raise ApiError(409, error.code, error.message) from None
    return _report_out(report)


@router.get("/api/baseline/report", operation_id="getBaselineReport")
def report_route(
    store: Annotated[BaselineStore, Depends(get_baseline_store)],
    inputs: Annotated[ExtractionInputs, Depends(get_extraction_inputs)],
    observations: Annotated[ObservationReader, Depends(get_observation_repository)],
    profiles: Annotated[BaselineProfileStore, Depends(get_profile_repository)],
    configs: Annotated[ScoringConfigReader, Depends(get_scoring_configs)],
    calibration: Annotated[CalibrationStore, Depends(get_calibration_store)],
) -> BaselineReportOut:
    report = baseline_report(
        store=store,
        observations=observations,
        profiles=profiles,
        configs=configs,
        calibration=calibration,
        inputs=inputs,
    )
    if report is None:
        raise ApiError(404, "no_baseline_report", "No completed baseline exists yet.")
    return _report_out(report)

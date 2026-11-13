"""`POST /api/sessions/{session_id}/complete`: closes a daily session once.

The first call snapshots the profile for the session and advances the re-check ladder. A repeat
returns the same completion time and changes nothing (200 both times)."""

from typing import Annotated

from fastapi import APIRouter, Depends

from nosolear.api.deps import (
    get_clock,
    get_observation_repository,
    get_profile_repository,
    get_recheck_store,
    get_session_completer,
    get_session_jobs,
    get_session_reader,
    get_settings,
    load_active_pack,
)
from nosolear.api.errors import ApiError
from nosolear.api.schemas import CompleteOut
from nosolear.app.complete_daily_session import complete_daily_session
from nosolear.domain.feedback import SessionNotAnalyzed, SessionNotDaily, SessionNotFound
from nosolear.domain.packs import PackError
from nosolear.domain.taxonomy import DEFAULT_TAXONOMY
from nosolear.ports.clock import Clock
from nosolear.ports.feedback import SessionJobStatus, SessionObservationReader, SessionReader
from nosolear.ports.plan import RecheckStore
from nosolear.ports.stores import ObservationReader, ProfileWriter, SessionCompleter
from nosolear.settings import Settings

router = APIRouter()


@router.post(
    "/api/sessions/{session_id}/complete",
    operation_id="completeDailySession",
    responses={
        404: {"description": "no such session"},
        409: {"description": "not a daily session, its analysis has not finished, or no pack"},
    },
)
def complete_session(
    session_id: str,
    settings: Annotated[Settings, Depends(get_settings)],
    clock: Annotated[Clock, Depends(get_clock)],
    sessions: Annotated[SessionReader, Depends(get_session_reader)],
    completer: Annotated[SessionCompleter, Depends(get_session_completer)],
    jobs: Annotated[SessionJobStatus, Depends(get_session_jobs)],
    observations: Annotated[SessionObservationReader, Depends(get_observation_repository)],
    all_observations: Annotated[ObservationReader, Depends(get_observation_repository)],
    profiles: Annotated[ProfileWriter, Depends(get_profile_repository)],
    rechecks: Annotated[RecheckStore, Depends(get_recheck_store)],
) -> CompleteOut:
    try:
        pack = load_active_pack(settings)
    except PackError:
        raise ApiError(409, "pack_unavailable", "The language pack could not be loaded.") from None
    try:
        done = complete_daily_session(
            session_id=session_id,
            sessions=sessions,
            sessions_writer=completer,
            jobs=jobs,
            observations=observations,
            all_observations=all_observations,
            profiles=profiles,
            rechecks=rechecks,
            taxonomy=DEFAULT_TAXONOMY,
            pack=pack,
            clock=clock,
        )
    except SessionNotFound:
        raise ApiError(404, "session_not_found", "No session has this id.") from None
    except SessionNotDaily:
        raise ApiError(409, "session_not_daily", "Only a daily session can be completed.") from None
    except SessionNotAnalyzed:
        raise ApiError(
            409,
            "session_not_analyzed",
            "The session is still being analyzed. It can be completed once its job has finished.",
        ) from None
    return CompleteOut(
        session_id=done.session_id,
        completed_at=done.completed_at,
        already_completed=done.already_completed,
    )

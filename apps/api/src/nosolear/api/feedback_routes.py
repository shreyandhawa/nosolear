"""`/api/sessions/{session_id}/feedback`: a daily session's feedback cards.

`POST` is the only route that can reach the coach: it makes or upgrades the cards, and it refuses
(409) while the session's analysis job is still running. `GET` only reads what was stored, so it
never calls the coach and never writes (§15). Errors are fixed sentences; a provider's text never
reaches a body."""

from typing import Annotated

from fastapi import APIRouter, Depends

from nosolear.api.deps import (
    Providers,
    get_feedback_store,
    get_observation_repository,
    get_profile_repository,
    get_providers,
    get_session_jobs,
    get_session_reader,
)
from nosolear.api.errors import ApiError
from nosolear.api.schemas import FeedbackItemOut, FeedbackOut, SkillFeedbackOut
from nosolear.app.generate_feedback import generate_feedback, read_feedback
from nosolear.domain.feedback import SessionNotAnalyzed, SessionNotDaily, SessionNotFound
from nosolear.domain.taxonomy import DEFAULT_TAXONOMY
from nosolear.ports.feedback import (
    FeedbackItem,
    FeedbackReport,
    FeedbackStore,
    SessionJobStatus,
    SessionObservationReader,
    SessionReader,
)
from nosolear.ports.plan import ProfileReader

router = APIRouter()


def _item_out(item: FeedbackItem) -> FeedbackItemOut:
    return FeedbackItemOut(
        id=item.id,
        error_key=item.error_key,
        message=item.message,
        model_text=item.model_text,
        source=item.source,
        fallback_reason=item.fallback_reason,
        attempt_id=item.attempt_id,
        start_ms=item.start_ms,
        end_ms=item.end_ms,
        word=item.word,
    )


def _feedback_out(report: FeedbackReport) -> FeedbackOut:
    return FeedbackOut(
        session_id=report.session_id,
        degraded=report.degraded,
        skills=[
            SkillFeedbackOut(
                skill=skill.skill.value,
                state=skill.state.value,
                item=None if skill.item is None else _item_out(skill.item),
            )
            for skill in report.skills
        ],
    )


@router.post(
    "/api/sessions/{session_id}/feedback",
    operation_id="generateFeedback",
    responses={
        404: {"description": "no such session"},
        409: {"description": "not a daily session, or its analysis has not finished"},
    },
)
def generate_session_feedback(
    session_id: str,
    sessions: Annotated[SessionReader, Depends(get_session_reader)],
    jobs: Annotated[SessionJobStatus, Depends(get_session_jobs)],
    observations: Annotated[SessionObservationReader, Depends(get_observation_repository)],
    profiles: Annotated[ProfileReader, Depends(get_profile_repository)],
    feedback: Annotated[FeedbackStore, Depends(get_feedback_store)],
    providers: Annotated[Providers, Depends(get_providers)],
) -> FeedbackOut:
    try:
        report = generate_feedback(
            session_id=session_id,
            sessions=sessions,
            jobs=jobs,
            observations=observations,
            profiles=profiles,
            feedback=feedback,
            coach=providers.coach,
            taxonomy=DEFAULT_TAXONOMY,
        )
    except SessionNotFound:
        raise ApiError(404, "session_not_found", "No session has this id.") from None
    except SessionNotDaily:
        raise ApiError(
            409, "session_not_daily", "Feedback is only made for a daily session."
        ) from None
    except SessionNotAnalyzed:
        raise ApiError(
            409,
            "session_not_analyzed",
            "The session is still being analyzed. Feedback is available once its job has finished.",
        ) from None
    return _feedback_out(report)


@router.get(
    "/api/sessions/{session_id}/feedback",
    operation_id="getFeedback",
    responses={404: {"description": "no feedback has been generated for this session"}},
)
def get_session_feedback(
    session_id: str,
    observations: Annotated[SessionObservationReader, Depends(get_observation_repository)],
    feedback: Annotated[FeedbackStore, Depends(get_feedback_store)],
) -> FeedbackOut:
    report = read_feedback(
        session_id=session_id,
        observations=observations,
        feedback=feedback,
        taxonomy=DEFAULT_TAXONOMY,
    )
    if report is None:
        raise ApiError(
            404, "feedback_not_generated", "No feedback has been generated for this session yet."
        )
    return _feedback_out(report)

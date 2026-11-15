"""The model voice: `POST` synthesizes stored text (a feedback item's model text or a content
item's text, never free text) through the cached, metered synthesizer and returns a clip id.
`GET` serves a cached clip only, so it never reaches the synthesizer."""

from typing import Annotated, Literal, cast

from fastapi import APIRouter, Depends, Path, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import Engine

from nosolear.api.deps import Services, get_services, get_settings
from nosolear.api.errors import ApiError
from nosolear.api.schemas import ErrorOut
from nosolear.domain.ssml import MAX_RATE_PERCENT
from nosolear.persistence.content_repository import ContentRepository
from nosolear.persistence.feedback_repositories import FeedbackRepository
from nosolear.persistence.tts_cache import TtsCacheRepository
from nosolear.settings import Settings

router = APIRouter()

WAV = "audio/wav"


class ModelVoiceIn(BaseModel):
    source: Literal["feedback_item", "content_item"]
    id: str = Field(min_length=1, max_length=64)
    rate_percent: int = Field(default=0, ge=-MAX_RATE_PERCENT, le=MAX_RATE_PERCENT)


class ModelVoiceOut(BaseModel):
    clip_id: str
    duration_ms: int


def _text(engine: Engine, body: ModelVoiceIn) -> str | None:
    if body.source == "feedback_item":
        return FeedbackRepository(engine).model_text(body.id)
    item = ContentRepository(engine).get(body.id)
    return None if item is None else item.text


@router.post(
    "/api/model-voice",
    operation_id="synthesizeModelVoice",
    responses={404: {"model": ErrorOut}},
)
def synthesize_model_voice(
    body: ModelVoiceIn,
    request: Request,
    services: Annotated[Services, Depends(get_services)],
) -> ModelVoiceOut:
    text = _text(cast(Engine, request.app.state.engine), body)
    if not text:
        raise ApiError(404, "no_model_text", "No stored item has model text with this id.")
    clip = services.providers.synthesizer.synthesize(text, rate_percent=body.rate_percent)
    return ModelVoiceOut(clip_id=clip.hash, duration_ms=clip.duration_ms)


@router.get(
    "/api/model-voice/{clip_id}",
    operation_id="getModelVoice",
    response_class=FileResponse,
    responses={200: {"content": {WAV: {}}}, 404: {"model": ErrorOut}},
)
def get_model_voice(
    clip_id: Annotated[str, Path(pattern=r"^[0-9a-f]{64}$")],
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> FileResponse:
    clip = TtsCacheRepository(cast(Engine, request.app.state.engine)).get(clip_id)
    path = None if clip is None else settings.data_dir / clip.path
    if path is None or not path.is_file():
        raise ApiError(404, "no_clip", "No cached clip has this id.")
    return FileResponse(path, media_type=WAV)
